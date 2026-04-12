"""Middleware chain for agent execution pipeline.

Hooks:
  before_llm      — pre-LLM call (Context Guard: ThreadData → Uploads → Compression)
  after_llm       — post-LLM call (Signal Handler: Title → Clarification)
  before_tools    — pre-tool call (Safety Gate: Security → Sandbox → LoopDetection)
  after_tools_all — after all tools in this turn (Sandbox release)
"""

from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nanodeer.agent.state import ThreadState


class Middleware(ABC):
    """Base middleware — subclasses only override hooks they need."""

    async def before_llm(self, state: "ThreadState") -> None:
        """Pre-LLM call — use for context setup."""
        pass

    async def after_llm(self, state: "ThreadState") -> None:
        """Post-LLM call — use for signal handling."""
        pass

    async def before_tools(
        self, state: "ThreadState", tool_name: str, tool_args: dict
    ) -> None:
        """Pre-tool call — use for validation/audit."""
        pass

    async def after_tools_all(self, state: "ThreadState") -> None:
        """After all tools in this turn — use for cleanup."""
        pass


class MiddlewareChain:
    """Per-hook independent middleware chain.

    Execution order:
      before_llm:     registration order (ThreadData → Uploads → Compression)
      after_llm:      reverse order (Clarification → Title)
      before_tools:    registration order (Security → Sandbox → LoopDetection)
      after_tools_all: reverse order (Sandbox release)
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

    async def before_llm(self, state: "ThreadState") -> None:
        """Execute before_llm chain in registration order."""
        for m in self._before_llm:
            await m.before_llm(state)

    async def after_llm(self, state: "ThreadState") -> None:
        """Execute after_llm chain in reverse order."""
        for m in reversed(self._after_llm):
            await m.after_llm(state)

    async def before_tools(
        self, state: "ThreadState", tool_name: str, tool_args: dict
    ) -> None:
        """Execute before_tools chain in registration order."""
        for m in self._before_tools:
            await m.before_tools(state, tool_name, tool_args)

    async def after_tools_all(self, state: "ThreadState") -> None:
        """Execute after_tools_all in reverse order."""
        for m in reversed(self._after_tools_all):
            await m.after_tools_all(state)
