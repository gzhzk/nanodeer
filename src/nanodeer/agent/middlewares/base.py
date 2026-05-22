"""Middleware chain for agent execution pipeline.

Hooks (all async generators — no sync versions):
  before_llm_streaming    — pre-LLM call
  after_llm_streaming     — post-LLM call
  before_tools_streaming  — pre-tool call
  after_tools_all_streaming — after all tools in this turn

All hooks receive (state, signals) where signals is TurnSignals — the
ephemeral per-turn context that dies at the end of each ReAct turn.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, AsyncGenerator

if TYPE_CHECKING:
    from nanodeer.agent.state import ThreadState, TurnSignals


class Middleware(ABC):
    """Base middleware — all hooks are async generators."""

    async def before_llm_streaming(self, state: "ThreadState", signals: "TurnSignals") -> AsyncGenerator[dict, None]:
        """Pre-LLM call. Override to inject context, create resources."""
        return
        yield  # make it an async generator

    async def after_llm_streaming(self, state: "ThreadState", signals: "TurnSignals") -> AsyncGenerator[dict, None]:
        """Post-LLM call. Override to inspect response, set WAIT."""
        return
        yield

    async def before_tools_streaming(
        self, state: "ThreadState", signals: "TurnSignals", tool_name: str, tool_args: dict
    ) -> AsyncGenerator[dict, None]:
        """Pre-tool call. Override to intercept, audit, or modify args."""
        return
        yield

    async def after_tools_all_streaming(self, state: "ThreadState", signals: "TurnSignals") -> AsyncGenerator[dict, None]:
        """After all tools in this turn. Override to cleanup, checkpoint."""
        return
        yield


class MiddlewareChain:
    """Per-hook middleware chain using streaming (async generator) interface.

    All hooks execute in registration order (forward order).
    """

    def __init__(
        self,
        before_llm: list[Middleware],
        after_llm: list[Middleware],
        before_tools: list[Middleware],
        after_tools_all: list[Middleware] | None = None,
    ):
        self._before_llm = before_llm
        self._after_llm = after_llm
        self._before_tools = before_tools
        self._after_tools_all = after_tools_all or []

    def iter_middlewares(self):
        """Iterate all unique middlewares across all hooks."""
        seen: set = set()
        for lst in [self._before_llm, self._after_llm, self._before_tools,
                    self._after_tools_all]:
            for mw in lst:
                if id(mw) not in seen:
                    seen.add(id(mw))
                    yield mw

    async def before_llm_streaming(self, state: "ThreadState", signals: "TurnSignals") -> AsyncGenerator[dict, None]:
        """Execute before_llm chain in streaming mode."""
        for m in self._before_llm:
            async for event in m.before_llm_streaming(state, signals):
                yield event

    async def after_llm_streaming(self, state: "ThreadState", signals: "TurnSignals") -> AsyncGenerator[dict, None]:
        """Execute after_llm chain in streaming mode."""
        for m in self._after_llm:
            async for event in m.after_llm_streaming(state, signals):
                yield event

    async def before_tools_streaming(
        self, state: "ThreadState", signals: "TurnSignals", tool_name: str, tool_args: dict
    ) -> AsyncGenerator[dict, None]:
        """Execute before_tools chain in streaming mode."""
        for m in self._before_tools:
            async for event in m.before_tools_streaming(state, signals, tool_name, tool_args):
                yield event

    async def after_tools_all_streaming(self, state: "ThreadState", signals: "TurnSignals") -> AsyncGenerator[dict, None]:
        """Execute after_tools_all chain in streaming mode."""
        for m in self._after_tools_all:
            async for event in m.after_tools_all_streaming(state, signals):
                yield event
