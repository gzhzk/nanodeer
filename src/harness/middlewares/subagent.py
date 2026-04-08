"""Subagent middleware - handles subagent spawning and execution."""

import asyncio
import re
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from ..subagents import run_subagents_in_parallel, SubagentType
from ..tools.subagent import format_subagent_results
from .base import Middleware


class SubagentMiddleware(Middleware):
    """Middleware for subagent task execution.

    Intercepts spawn_subagent calls, collects pending tasks,
    and executes them in parallel when agent requests results.
    Also intercepts get_subagent_results to inject actual results.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool] | None = None,
        max_concurrent: int = 3,
        timeout: int = 900,
    ):
        """Initialize SubagentMiddleware.

        Args:
            llm: LLM to use for subagent execution.
            tools: Available tools for subagents.
            max_concurrent: Maximum concurrent subagents (default 3).
            timeout: Timeout per subagent in seconds (default 15 min).
        """
        self.llm = llm
        self.tools = tools or []
        self.max_concurrent = max_concurrent
        self.timeout = timeout

    async def before_agent_start(self, state: Any) -> None:
        """Initialize subagent tracking in state."""
        if not hasattr(state, "pending_subagent_tasks"):
            state.pending_subagent_tasks = []
        if not hasattr(state, "subagent_results"):
            state.subagent_results = []

    async def after_tool_call(
        self,
        state: Any,
        tool_name: str,
        tool_args: dict[str, Any],
        result: str,
    ) -> str:
        """Intercept spawn_subagent and get_subagent_results calls."""
        if tool_name == "spawn_subagent":
            # Collect pending subagent tasks
            pending = getattr(state, "pending_subagent_tasks", [])
            pending.append({
                "subagent_id": self._extract_subagent_id(result),
                "name": tool_args.get("name", "worker"),
                "task": tool_args.get("task", ""),
                "subagent_type": tool_args.get("subagent_type", "general"),
            })
            state.pending_subagent_tasks = pending
            return result

        elif tool_name == "get_subagent_results":
            # Replace placeholder with actual results
            if "[SUBAGENT_RESULTS_PLACEHOLDER]" in result:
                results = getattr(state, "subagent_results", [])
                return format_subagent_results(results)
            return result

        return result

    def _extract_subagent_id(self, result: str) -> str:
        """Extract subagent ID from spawn result."""
        match = re.search(r"subagent-[a-f0-9]+", result)
        return match.group(0) if match else f"subagent-{id(result)}"

    async def after_agent_end(self, state: Any) -> None:
        """Execute pending subagents in parallel after agent finishes."""
        pending = getattr(state, "pending_subagent_tasks", [])
        if not pending:
            return

        # Filter by max_concurrent
        to_run = pending[:self.max_concurrent]
        remaining = pending[self.max_concurrent:]

        if not to_run:
            return

        # Build subagent specs
        specs = []
        for spec in to_run:
            # Determine tools based on subagent type
            if spec.get("subagent_type") == SubagentType.BASH:
                # Bash-only: need to filter to bash tool
                from ..tools.shell import bash
                tools = [bash]
            else:
                tools = self.tools

            specs.append({
                "subagent_id": spec["subagent_id"],
                "name": spec["name"],
                "task": spec["task"],
                "tools": tools,
            })

        # Execute in parallel
        results = await run_subagents_in_parallel(specs, self.llm, self.timeout)

        # Store results
        existing = getattr(state, "subagent_results", [])
        state.subagent_results = existing + results

        # Keep remaining for next round
        state.pending_subagent_tasks = remaining
