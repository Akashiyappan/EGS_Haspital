"""LangGraph-powered hospital assistant agent.

Executes the LangGraph decision workflow, coordinating bounded iterations,
tool calls, slot scheduling, data gathering, safety guardrails, and final
structured JSON answers.
"""

import asyncio
import logging
import time
from typing import Any

from app.ai.graph import (
    AgentRun,
    HospitalGraphState,
    hospital_graph,
)
from app.ai.llm import LLMClient, LLMError
from app.ai.tools import ToolContext, ToolRegistry
from app.core.config import settings

logger = logging.getLogger(__name__)


class SymptomAgent:
    """Agent running on LangGraph for automatic decision making and tool calling."""

    def __init__(self, llm: LLMClient | None, registry: ToolRegistry) -> None:
        self.llm = llm
        self.registry = registry

    async def run(self, messages: list[dict[str, Any]], ctx: ToolContext) -> AgentRun:
        start = time.monotonic()
        run = AgentRun(result=None, termination="max_iterations")
        initial_state: HospitalGraphState = {
            "messages": list(messages),
            "context": ctx,
            "llm": self.llm,
            "registry": self.registry,
            "route": "",
            "result": None,
            "tool_traces": [],
            "iterations": 0,
            "tokens": 0,
            "termination": "max_iterations",
            "unknown_tool_retries": 0,
            "latest_response": None,
        }
        try:
            async with asyncio.timeout(settings.AI_TIMEOUT_SECONDS):
                final_state = await hospital_graph.ainvoke(initial_state)
                run.result = final_state.get("result")
                run.termination = final_state.get("termination", "completed")
                run.tool_traces = final_state.get("tool_traces", [])
                run.iterations = final_state.get("iterations", 0)
                run.tokens = final_state.get("tokens", 0)
        except TimeoutError:
            run.termination = "timeout"
        except LLMError as exc:
            run.termination = "model_error"
            logger.warning("AI model error: %s", exc)

        run.latency_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "LangGraph agent finished termination=%s iterations=%s tokens=%s tools=%s latency_ms=%s",
            run.termination,
            run.iterations,
            run.tokens,
            [t.name for t in run.tool_traces],
            run.latency_ms,
        )
        return run


# Alias for explicit naming
HospitalLangGraphAgent = SymptomAgent
