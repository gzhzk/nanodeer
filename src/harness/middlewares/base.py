"""Middleware chain for agent execution pipeline.

Middlewares intercept at hooks: before_agent_start, before_tool_call, etc.
before_* hooks run forward, after_* hooks run in reverse (reverse cleanup).
"""
from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harness.agent.state import ThreadState


class Middleware(ABC):
    """Interceptor hooks at agent execution lifecycle points."""

    async def before_agent_start(self, state: "ThreadState") -> None: ...

    async def after_agent_end(self, state: "ThreadState") -> None: ...

    async def before_tool_call(
        self, state: "ThreadState", tool_name: str, tool_args: dict
    ) -> None: ...

    async def after_tool_call(
        self, state: "ThreadState", tool_name: str, tool_args: dict, result: str
    ) -> None: ...

    async def on_error(self, state: "ThreadState", error: Exception) -> None: ...


class MiddlewareChain:
    """Middleware chain with ordered execution.

    before_* hooks execute in registration order.
    after_* hooks execute in reverse order (reverse cleanup pattern).
    """

    def __init__(self, middlewares: list[Middleware]):
        self.middlewares = middlewares

    async def before_agent_start(self, state: "ThreadState") -> None:
        for m in self.middlewares:
            await m.before_agent_start(state)

    async def after_agent_end(self, state: "ThreadState") -> None:
        for m in reversed(self.middlewares):
            await m.after_agent_end(state)

    async def before_tool_call(
        self, state: "ThreadState", tool_name: str, tool_args: dict
    ) -> None:
        for m in self.middlewares:
            await m.before_tool_call(state, tool_name, tool_args)

    async def after_tool_call(
        self, state: "ThreadState", tool_name: str, tool_args: dict, result: str
    ) -> None:
        for m in reversed(self.middlewares):
            await m.after_tool_call(state, tool_name, tool_args, result)

    async def on_error(self, state: "ThreadState", error: Exception) -> None:
        for m in reversed(self.middlewares):
            await m.on_error(state, error)
