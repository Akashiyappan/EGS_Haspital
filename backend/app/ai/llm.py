"""LLM client abstraction. The agent depends on `LLMClient` only, so the
provider (Groq today) can be swapped or faked in tests."""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)

_RETRY_AFTER_RE = re.compile(r"try again in (?:([\d.]+)m)?([\d.]+)s")
_MAX_RATE_LIMIT_WAIT_S = 5.0


class LLMError(Exception):
    """The provider failed (timeout, outage, rate limit, invalid request)."""


class UnknownToolCallError(LLMError):
    """The model tried to call a tool that was not offered (provider rejected it)."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None,
        tool_choice: str = "auto",
    ) -> LLMResponse: ...


class GroqLLMClient:
    def __init__(self) -> None:
        from groq import AsyncGroq

        # SDK retries disabled: rate-limit handling below is the single owner of
        # retry policy (same approach as the reference claims agent).
        self._client = AsyncGroq(
            api_key=settings.GROQ_API_KEY.get_secret_value(),
            max_retries=0,
            timeout=settings.AI_TIMEOUT_SECONDS,
        )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        import groq

        kwargs: dict[str, Any] = {
            "model": settings.GROQ_MODEL,
            "messages": messages,
            "temperature": settings.AI_TEMPERATURE,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        for attempt in range(2):
            try:
                response = await self._client.chat.completions.create(**kwargs)
                break
            except groq.RateLimitError as exc:
                wait = _retry_after(str(exc))
                if attempt == 1 or wait > _MAX_RATE_LIMIT_WAIT_S:
                    raise LLMError("AI provider rate limit reached") from exc
                logger.warning("AI provider rate limited; retrying in %.1fs", wait)
                await asyncio.sleep(wait)
            except groq.BadRequestError as exc:
                if "which was not in request" in str(exc) or "tool call validation" in str(exc):
                    raise UnknownToolCallError("Model called an unavailable tool") from exc
                raise LLMError(f"AI provider rejected the request ({exc.status_code})") from exc
            except (groq.APITimeoutError, groq.APIConnectionError) as exc:
                raise LLMError("AI provider is unreachable") from exc
            except groq.APIStatusError as exc:
                raise LLMError(f"AI provider error ({exc.status_code})") from exc

        message = response.choices[0].message
        usage = response.usage
        return LLMResponse(
            content=message.content,
            tool_calls=[
                ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments or "{}")
                for tc in (message.tool_calls or [])
            ],
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )


def _retry_after(message: str) -> float:
    match = _RETRY_AFTER_RE.search(message)
    if not match:
        return 2.0
    minutes = float(match.group(1)) if match.group(1) else 0.0
    return minutes * 60 + float(match.group(2)) + 0.5


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """FastAPI dependency; tests override it with a scripted fake."""
    global _client
    from app.core.exceptions import ServiceUnavailableError

    if not settings.ai_configured:
        raise ServiceUnavailableError(
            "The AI assistant is not configured on this server", code="ai_unavailable"
        )
    if _client is None:
        _client = GroqLLMClient()
    return _client
