"""SubagentMiddleware — manages parallel subagent execution with concurrency control.

Risks managed:
- Concurrency exhaustion: enforce max_concurrent limit
- Timeout: enforce timeout on subagent execution
- State tracking: collect pending tasks, inject results

before_tools: collect spawn_subagent calls into pending queue
after_tools: intercept get_subagent_results, execute pending, inject results
"""

import asyncio
import time
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from ..state import ThreadState
from ...subagents.runner import run_subagents_in_parallel, generate_subagent_id
from .base import Middleware


class SubagentMiddleware(Middleware):
    """Manages parallel subagent execution with risk controls.

    Collects spawn_subagent calls and executes them in parallel
    when get_subagent_results is called, enforcing concurrency
    and timeout limits.
    """

    MAX_CONCURRENT = 3
    DEFAULT_TIMEOUT = 900  # 15 minutes

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        max_concurrent: int | None = None,
        timeout: int | None = None,
    ):
        self._llm = llm
        self.max_concurrent = max_concurrent or self.MAX_CONCURRENT
        self.timeout = timeout or self.DEFAULT_TIMEOUT

        # Per-thread pending subagent queue
        self._pending: dict[str, list[dict[str, Any]]] = {}
        self._results: dict[str, list[dict[str, Any]]] = {}

    @property
    def llm(self) -> BaseChatModel:
        if self._llm is None:
            raise RuntimeError("SubagentMiddleware.llm not set: pass llm to __init__ or call set_llm()")
        return self._llm

    def set_llm(self, llm: BaseChatModel) -> None:
        self._llm = llm

    def _get_queue(self, thread_id: str) -> tuple[list, list]:
        """Get or create pending/results queues for thread."""
        if thread_id not in self._pending:
            self._pending[thread_id] = []
            self._results[thread_id] = []
        return self._pending[thread_id], self._results[thread_id]

    async def before_tools(
        self, state: ThreadState, tool_name: str, tool_args: dict
    ) -> None:
        """Collect spawn_subagent calls into pending queue."""
        if tool_name != "spawn_subagent":
            return

        thread_id = state.thread_id or "default"
        pending, _ = self._get_queue(thread_id)

        subagent_id = generate_subagent_id()
        spec = {
            "subagent_id": subagent_id,
            "name": tool_args.get("name", "subagent"),
            "task": tool_args.get("task", ""),
            "tools": tool_args.get("tools", []),
        }
        pending.append(spec)

        # Enforce concurrency limit
        if len(pending) > self.max_concurrent:
            # Kick off oldest batch to stay under limit
            excess = pending[:-self.max_concurrent]
            pending = pending[-self.max_concurrent:]
            self._pending[thread_id] = pending
            await self._execute_batch(excess, thread_id)

    async def after_tools(
        self, state: ThreadState, tool_name: str, tool_args: dict, result: str
    ) -> str:
        """Intercept get_subagent_results, execute pending, inject results."""
        if tool_name != "get_subagent_results":
            return result

        thread_id = state.thread_id or "default"
        pending, results = self._get_queue(thread_id)

        # Execute all pending subagents in parallel
        if pending:
            await self._execute_batch(pending, thread_id)
            self._pending[thread_id] = []
            pending = []
            _, results = self._get_queue(thread_id)

        if not results:
            return "[No subagent results available]"

        return self._format_results(results)

    async def _execute_batch(self, specs: list[dict[str, Any]], thread_id: str) -> None:
        """Execute a batch of subagents in parallel with concurrency limit."""
        if not specs:
            return

        results = await run_subagents_in_parallel(
            subagent_specs=specs,
            llm=self.llm,
            timeout=self.timeout,
            max_iterations=10,
        )
        self._results[thread_id].extend(results)

    def _format_results(self, results: list[dict[str, Any]]) -> str:
        """Format subagent results for injection into conversation."""
        lines = ["<subagent_results>"]
        for r in results:
            status = r.get("status", "unknown")
            name = r.get("name", "subagent")
            output = r.get("output", "")
            error = r.get("error", "")
            duration = r.get("duration_seconds", 0)

            lines.append(f"## {name} ({status}) [{duration:.1f}s]")
            if error:
                lines.append(f"Error: {error}")
            else:
                lines.append(f"Output: {output[:500]}")
            lines.append("")

        lines.append("</subagent_results>")
        return "\n".join(lines)