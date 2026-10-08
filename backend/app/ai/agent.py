"""Tool-calling agent loop for the symptom assistant.

Mirrors the reference claims agent: bounded iterations and token budget, tool
calls executed by the backend, unknown-tool attempts recorded rather than
crashing, and a final structured JSON answer. Differences: async, tool
arguments are schema-validated, and a final answer is forced (with tools
disabled) when the budget runs out.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.ai.llm import LLMClient, LLMError, UnknownToolCallError
from app.ai.schemas import AssistantResult
from app.ai.tools import ToolContext, ToolRegistry, ToolTrace
from app.core.config import settings

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
_FINALIZE_INSTRUCTION = (
    "Stop using tools now. Reply with ONLY the final JSON object in the required format."
)


@dataclass
class AgentRun:
    result: AssistantResult | None
    termination: str
    tool_traces: list[ToolTrace] = field(default_factory=list)
    iterations: int = 0
    tokens: int = 0
    latency_ms: int = 0


def parse_result(content: str | None) -> AssistantResult | None:
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        if not isinstance(data, dict):
            return None
        return AssistantResult.model_validate(_coerce(data))
    except (json.JSONDecodeError, ValidationError):
        return None


def _coerce(data: dict[str, Any]) -> dict[str, Any]:
    """Tolerate common model slips (string ids, overlong lists) before validation."""
    limits = {
        "possible_concerns": 5,
        "recommended_specializations": 5,
        "recommended_doctor_ids": 5,
        "next_steps": 5,
        "follow_up_questions": 3,
    }
    for key, limit in limits.items():
        value = data.get(key)
        if isinstance(value, list):
            data[key] = [str(v)[:300] for v in value if str(v).strip()][:limit]
    ids = []
    for value in data.get("recommended_doctor_ids") or []:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    data["recommended_doctor_ids"] = ids
    if data.get("urgency") not in ("emergency", "urgent", "routine", "self_care"):
        data["urgency"] = "routine"
    data.pop("emergency_message", None)
    data.pop("disclaimer", None)
    return data


class SymptomAgent:
    def __init__(self, llm: LLMClient, registry: ToolRegistry) -> None:
        self.llm = llm
        self.registry = registry

    async def run(self, messages: list[dict[str, Any]], ctx: ToolContext) -> AgentRun:
        start = time.monotonic()
        run = AgentRun(result=None, termination="max_iterations")
        try:
            async with asyncio.timeout(settings.AI_TIMEOUT_SECONDS):
                await self._loop(messages, ctx, run)
        except TimeoutError:
            run.termination = "timeout"
        except LLMError as exc:
            run.termination = "model_error"
            logger.warning("AI model error: %s", exc)
        run.latency_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "AI agent finished termination=%s iterations=%s tokens=%s tools=%s latency_ms=%s",
            run.termination,
            run.iterations,
            run.tokens,
            [t.name for t in run.tool_traces],
            run.latency_ms,
        )
        return run

    async def _loop(self, messages: list[dict[str, Any]], ctx: ToolContext, run: AgentRun) -> None:
        tools = self.registry.schemas()
        unknown_tool_retries = 0
        while run.iterations < settings.AI_MAX_ITERATIONS and run.tokens < settings.AI_MAX_TOKENS:
            run.iterations += 1
            try:
                response = await self.llm.complete(messages, tools=tools)
            except UnknownToolCallError:
                if unknown_tool_retries:
                    raise
                unknown_tool_retries += 1
                run.tool_traces.append(ToolTrace(name="<unknown>", ok=False, latency_ms=0))
                messages.append(
                    {
                        "role": "system",
                        "content": "You may only call these tools: "
                        + ", ".join(self.registry.names),
                    }
                )
                continue
            run.tokens += response.prompt_tokens + response.completion_tokens

            if not response.tool_calls:
                run.result = parse_result(response.content)
                run.termination = "completed"
                if run.result is None:  # one repair attempt for malformed output
                    run.result = await self._finalize(messages, response.content, run)
                    run.termination = "repaired" if run.result else "invalid_output"
                return

            messages.append(
                {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.name, "arguments": call.arguments},
                        }
                        for call in response.tool_calls
                    ],
                }
            )
            for call in response.tool_calls:
                result, trace = await self.registry.execute(call.name, call.arguments, ctx)
                run.tool_traces.append(trace)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, default=str),
                    }
                )

        # Budget exhausted while still calling tools: ask for the answer without tools.
        run.result = await self._finalize(messages, None, run)
        run.termination = "completed_after_budget" if run.result else "max_iterations"

    async def _finalize(
        self, messages: list[dict[str, Any]], previous: str | None, run: AgentRun
    ) -> AssistantResult | None:
        followup = list(messages)
        if previous:
            followup.append({"role": "assistant", "content": previous})
        followup.append({"role": "system", "content": _FINALIZE_INSTRUCTION})
        response = await self.llm.complete(followup, tools=None)
        run.iterations += 1
        run.tokens += response.prompt_tokens + response.completion_tokens
        return parse_result(response.content)
