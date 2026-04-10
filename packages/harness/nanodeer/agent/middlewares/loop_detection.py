"""LoopDetectionMiddleware — prevents infinite tool call loops.

Detects repetitive tool calls using MD5 hash of (tool_name + sorted args).
Thread-safe with per-thread locks.

Reference: DeerFlow LoopDetectionMiddleware.
"""

import asyncio
import hashlib
import json
import logging
from collections import OrderedDict
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from ..state import ThreadState
from .base import Middleware

logger = logging.getLogger(__name__)


class LoopDetectionMiddleware(Middleware):
    """Detects and breaks repetitive tool call loops.

    Uses a sliding window hash of tool calls (name + args, order-independent).
    Thread-safe with per-thread locks.

    Args:
        warn_threshold: Inject warning HumanMessage after N identical calls.
        hard_limit: Strip tool_calls after M identical calls (forces end).
        window_size: Max tool calls to track per thread.
        max_threads: Max threads before LRU eviction.
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

        # thread_id -> OrderedDict[hash, count], plus access order tracking
        self._history: dict[str, list[tuple[str, int]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, thread_id: str) -> asyncio.Lock:
        if thread_id not in self._locks:
            self._locks[thread_id] = asyncio.Lock()
        return self._locks[thread_id]

    def _hash_tool_calls(self, tool_calls: list[dict]) -> str:
        """Hash tool calls in order-independent way.

        Sorts by (name, sorted_args) so same calls in different order → same hash.
        """
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
            # LRU: evict oldest if at capacity
            if len(self._history) >= self.max_threads:
                oldest = next(iter(self._history))
                del self._history[oldest]
            self._history[thread_id] = []
        return self._history[thread_id]

    async def before_tool_call(
        self, state: ThreadState, tool_name: str, tool_args: dict
    ) -> None:
        """Check for repetitive tool calls before execution."""
        thread_id = getattr(state, "thread_id", None) or "default"

        async with self._get_lock(thread_id):
            history = self._get_history(thread_id)
            current_hash = self._hash_tool_calls([{"name": tool_name, "args": tool_args}])

            # Find existing entry
            found_idx = None
            for i, (h, _) in enumerate(history):
                if h == current_hash:
                    found_idx = i
                    break

            if found_idx is None:
                # New tool call — add to history
                history.append((current_hash, 1))
            else:
                # Repeat — increment count
                old_hash, old_count = history[found_idx]
                history[found_idx] = (old_hash, old_count + 1)
                count = old_count + 1

                logger.warning(
                    f"LoopDetection: repeated tool call detected "
                    f"thread={thread_id} tool={tool_name} count={count}"
                )

                if count == self.warn_threshold:
                    # Inject warning as HumanMessage (not SystemMessage — avoids
                    # Anthropic "multiple non-consecutive system messages" error)
                    warning = (
                        f"⚠️ Warning: The tool `{tool_name}` has been called "
                        f"{count} times with identical arguments. "
                        f"Consider a different approach or stopping to avoid a loop."
                    )
                    self._inject_human_message(state, warning)

                elif count >= self.hard_limit:
                    # Hard stop — strip tool_calls from last AI message
                    self._strip_tool_calls(state)
                    logger.warning(
                        f"LoopDetection: hard limit reached, stripped tool_calls "
                        f"thread={thread_id} tool={tool_name} count={count}"
                    )

            # Trim window to window_size (keep most recent)
            if len(history) > self.window_size:
                history[:] = history[-self.window_size:]

    def _inject_human_message(self, state: ThreadState, content: str) -> None:
        """Inject a HumanMessage into the state's messages list."""
        if hasattr(state, "messages"):
            state.messages.append(HumanMessage(content=content))

    def _strip_tool_calls(self, state: ThreadState) -> None:
        """Strip tool_calls from the last AIMessage in state.messages.

        This causes _should_continue to return "end" on next iteration,
        breaking the tool call loop.
        """
        if not hasattr(state, "messages"):
            return

        for msg in reversed(state.messages):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                # Create new AIMessage without tool_calls
                stripped = AIMessage(
                    content=msg.content,
                    tool_calls=[],  # type: ignore
                    id=msg.id,
                    name=msg.name,
                    usage_metadata=getattr(msg, "usage_metadata", None),
                )
                # Replace in place
                for i, m in enumerate(state.messages):
                    if m is msg:
                        state.messages[i] = stripped
                        break
                break
