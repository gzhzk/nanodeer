"""LoopDetectionMiddleware — detects repetitive tool call loops.

Sets next_action="end" when hard limit is reached. When warn threshold is
reached, signals via metadata["loop_warning"] so the prompt layer can inject
a reminder — keeping the message history clean.
"""

import asyncio
import hashlib
import json
import logging
from typing import Any

from ..state import ThreadState
from .base import Middleware

logger = logging.getLogger(__name__)


class LoopDetectionMiddleware(Middleware):
    """Detects and breaks repetitive tool call loops.

    Uses a sliding window hash of tool calls (name + args, order-independent).
    Thread-safe with per-thread locks.

    warn_threshold: set metadata signal for prompt layer to remind LLM
    hard_limit: set next_action="end" to terminate the graph
    """

    def __init__(
        self,
        warn_threshold: int = 3,
        hard_limit: int = 5,
        window_size: int = 20,
        max_threads: int = 100,
    ):
        self.warn_threshold = warn_threshold
        self.hard_limit = hard_limit
        self.window_size = window_size
        self.max_threads = max_threads

        self._history: dict[str, list[tuple[str, int]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, thread_id: str) -> asyncio.Lock:
        if thread_id not in self._locks:
            self._locks[thread_id] = asyncio.Lock()
        return self._locks[thread_id]

    def _hash_tool_calls(self, tool_calls: list[dict]) -> str:
        """Hash tool calls in order-independent way."""
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

    async def before_tools(
        self, state: ThreadState, tool_name: str, tool_args: dict
    ) -> None:
        """Check for repetitive tool calls before execution."""
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

                if count == self.warn_threshold:
                    # Signal via metadata — prompt layer reads this and injects
                    # a reminder into the system prompt. Message history stays clean.
                    state.metadata["loop_warning"] = {
                        "tool": tool_name,
                        "count": count,
                        "threshold": self.warn_threshold,
                    }

                elif count >= self.hard_limit:
                    state.metadata.pop("loop_warning", None)
                    state.next_action = "end"
                    logger.warning(
                        f"LoopDetection: hard limit reached, setting next_action=end "
                        f"thread={thread_id} tool={tool_name} count={count}"
                    )

            if len(history) > self.window_size:
                history[:] = history[-self.window_size:]