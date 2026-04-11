"""Middleware chain for agent execution pipeline.

Hooks:
  before_llm / after_llm               — around LLM node
  before_tools / after_tools           — around each tool call
  after_tools_all                      — after all tools in this turn finish
  on_error                             — on exception (independent reverse chain)
"""

from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nanodeer.agent.state import ThreadState


class Middleware(ABC):
    """Each middleware only override the hooks it needs."""

    async def before_llm(self, state: "ThreadState") -> None:
        pass

    async def after_llm(self, state: "ThreadState") -> None:
        pass

    async def before_tools(
        self, state: "ThreadState", tool_name: str, tool_args: dict
    ) -> None:
        pass

    async def after_tools(
        self, state: "ThreadState", tool_name: str, tool_args: dict, result: str
    ) -> str:
        return result

    async def after_tools_all(self, state: "ThreadState") -> None:
        """Called once after all tool calls in this turn have been processed."""
        pass

    async def on_error(self, state: "ThreadState", error: Exception) -> None:
        pass


class MiddlewareChain:
    """Per-hook independent middleware chain.

    Each middleware only participates in hooks it actually implements.
    - before_* runs in registration order
    - after_* / after_tools_all run in reverse registration order
    - on_error runs in reverse order (independent list)

    Hook execution order (confirmed):
      before_llm:    ThreadData → Sandbox → Uploads → Memory → Plan →
                      Compression → Subagent → LoopDetection → Reflection

      after_llm:     Title → Memory → Plan → Subagent → Reflection
                      (reversed of: Reflection → Subagent → Plan → Memory → Title)

      before_tools:  Security → Sandbox → LoopDetection → Reflection

      after_tools:   Reflection → Plan → Subagent → Clarification → Sandbox
                      (reversed of: Sandbox → Clarification → Subagent → Plan → Reflection)

      after_tools_all: (reversed) — Sandbox releases container here
    """

    def __init__(
        self,
        before_llm: list[Middleware],
        after_llm: list[Middleware],
        before_tools: list[Middleware],
        after_tools: list[Middleware],
        after_tools_all: list[Middleware] | None = None,
        on_error: list[Middleware] | None = None,
    ):
        self._before_llm = before_llm
        self._after_llm = after_llm
        self._before_tools = before_tools
        self._after_tools = after_tools
        self._after_tools_all = after_tools_all or []
        self._on_error = on_error or []

    def iter_middlewares(self):
        """Iterate all unique middlewares across all hooks."""
        seen: set = set()
        for lst in [self._before_llm, self._after_llm, self._before_tools,
                    self._after_tools, self._after_tools_all]:
            for mw in lst:
                if id(mw) not in seen:
                    seen.add(id(mw))
                    yield mw

    async def before_llm(self, state: "ThreadState") -> None:
        for m in self._before_llm:
            await m.before_llm(state)

    async def after_llm(self, state: "ThreadState") -> None:
        for m in reversed(self._after_llm):
            await m.after_llm(state)

    async def before_tools(
        self, state: "ThreadState", tool_name: str, tool_args: dict
    ) -> None:
        for m in self._before_tools:
            await m.before_tools(state, tool_name, tool_args)

    async def after_tools(
        self, state: "ThreadState", tool_name: str, tool_args: dict, result: str
    ) -> str:
        current = result
        for m in reversed(self._after_tools):
            current = await m.after_tools(state, tool_name, tool_args, current)
        return current

    async def after_tools_all(self, state: "ThreadState") -> None:
        for m in reversed(self._after_tools_all):
            await m.after_tools_all(state)

    async def on_error(self, state: "ThreadState", error: Exception) -> None:
        for m in reversed(self._on_error):
            await m.on_error(state, error)
