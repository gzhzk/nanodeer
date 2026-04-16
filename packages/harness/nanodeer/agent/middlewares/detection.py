"""DetectionMiddleware — health checks, loop detection, and timeout tracking.

before_llm:    checks sandbox liveness.
before_tools:  marks tool start time + detects repetitive tool call loops
               (merged from former LoopDetectionMiddleware).
"""

import asyncio
import hashlib
import json
import logging
import time

from nanodeer.agent.state import NextAction, ThreadState

from .base import Middleware

logger = logging.getLogger(__name__)


class DetectionMiddleware(Middleware):
    """Detects health issues, tool call loops, and tracks execution time.

    Writes:
      metadata["health_error"]  — set if sandbox released
      metadata["_tool_start"]    — timestamp before tool runs
      metadata["loop_warning"]  — loop warn signal for prompt layer
    """

    def __init__(
        self,
        loop_warn_threshold: int = 3,
        loop_hard_limit: int = 5,
        loop_window_size: int = 20,
        max_threads: int = 100,
    ):
        self.loop_warn_threshold = loop_warn_threshold
        self.loop_hard_limit = loop_hard_limit
        self.loop_window_size = loop_window_size
        self.max_threads = max_threads

        self._history: dict[str, list[tuple[str, int]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, thread_id: str) -> asyncio.Lock:
        if thread_id not in self._locks:
            self._locks[thread_id] = asyncio.Lock()
        return self._locks[thread_id]

    def _hash_tool_calls(self, tool_calls: list[dict]) -> str:
        normalized = [
            {"name": tc.get("name", ""), "args": tc.get("args", {})}
            for tc in tool_calls
        ]
        normalized.sort(
            key=lambda tc: (tc["name"], json.dumps(tc["args"], sort_keys=True, default=str))
        )
        blob = json.dumps(normalized, sort_keys=True, default=str)
        return hashlib.md5(blob.encode()).hexdigest()[:12]

    def _get_history(self, thread_id: str) -> list[tuple[str, int]]:
        if thread_id not in self._history:
            if len(self._history) >= self.max_threads:
                oldest = next(iter(self._history))
                del self._history[oldest]
            self._history[thread_id] = []
        return self._history[thread_id]

    async def before_llm(self, state: ThreadState) -> None:
        if state.sandbox and state.sandbox.container_id:
            if state.sandbox.status == "released":
                state.metadata["health_error"] = "sandbox_released"

    async def before_tools(
        self, state: ThreadState, tool_name: str, tool_args: dict
    ) -> None:
        # Mark tool start time — HandlingMiddleware reads this to detect timeout.
        state.metadata["_tool_start"] = time.monotonic()

        # Loop detection: sliding window hash
        thread_id = getattr(state, "thread_id", None) or "default"

        async with self._get_lock(thread_id):
            history = self._get_history(thread_id)
            current_hash = self._hash_tool_calls([{"name": tool_name, "args": tool_args}])

            found_idx = None
            for i, (h, _) in enumerate(history):
                if h == current_hash:
                    found_idx = i
                    break

            if found_idx is None:
                history.append((current_hash, 1))
            else:
                old_hash, old_count = history[found_idx]
                history[found_idx] = (old_hash, old_count + 1)
                count = old_count + 1

                logger.warning(
                    f"LoopDetection: repeated tool call detected "
                    f"thread={thread_id} tool={tool_name} count={count}"
                )

                if count == self.loop_warn_threshold:
                    state.metadata["loop_warning"] = {
                        "tool": tool_name,
                        "count": count,
                        "threshold": self.loop_warn_threshold,
                    }
                elif count >= self.loop_hard_limit:
                    state.metadata.pop("loop_warning", None)
                    state.next_action = NextAction.END
                    logger.warning(
                        f"LoopDetection: hard limit reached, setting next_action=END "
                        f"thread={thread_id} tool={tool_name} count={count}"
                    )

            if len(history) > self.loop_window_size:
                history[:] = history[-self.loop_window_size:]
