"""Tool registry. The model only sees tools registered here; every call is
validated against the tool's Pydantic parameter model before it runs, and
failures are returned to the model as structured errors instead of raising."""

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


class ToolError(Exception):
    """A tool could not complete; the message is shown to the model."""


@dataclass
class ToolContext:
    db: AsyncSession
    now: datetime
    # Every doctor id a tool returned during this run. The final answer may only
    # recommend doctors from this set.
    seen_doctor_ids: set[int] = field(default_factory=set)


@dataclass(frozen=True)
class ToolTrace:
    name: str
    ok: bool
    latency_ms: int


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    Params: ClassVar[type[BaseModel]]

    @abstractmethod
    async def run(self, ctx: ToolContext, params: Any) -> dict[str, Any]: ...

    def schema(self) -> dict[str, Any]:
        parameters = self.Params.model_json_schema()
        parameters.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    async def execute(
        self, name: str, raw_arguments: str, ctx: ToolContext
    ) -> tuple[dict[str, Any], ToolTrace]:
        start = time.monotonic()
        tool = self._tools.get(name)
        ok = False
        try:
            if tool is None:
                raise ToolError(f"Unknown tool '{name}'. Available tools: {', '.join(self.names)}")
            try:
                arguments = json.loads(raw_arguments or "{}")
                if not isinstance(arguments, dict):
                    raise ToolError("Tool arguments must be a JSON object")
                params = tool.Params.model_validate(arguments)
            except (json.JSONDecodeError, ValidationError) as exc:
                raise ToolError(f"Invalid arguments for {name}: {exc}") from exc
            result = await tool.run(ctx, params)
            ok = True
        except ToolError as exc:
            result = {"error": str(exc)}
        except AppError as exc:  # domain errors (not found, invalid) are safe to surface
            result = {"error": exc.message}
        except Exception:
            logger.exception("AI tool %s failed", name)
            result = {"error": "The tool failed unexpectedly."}
        trace = ToolTrace(name=name, ok=ok, latency_ms=int((time.monotonic() - start) * 1000))
        logger.info("AI tool call name=%s ok=%s latency_ms=%s", name, ok, trace.latency_ms)
        return result, trace
