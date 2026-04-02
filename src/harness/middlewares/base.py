"""Base class for Harness middlewares.

Middlewares intercept the agent execution pipeline at various hooks.
They can read/write state and perform side effects (acquire resources,
validate inputs, update memory, etc).
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harness.agent.state import ThreadState


class Middleware(ABC):
    """Abstract base class for all Harness middlewares.

    Middlewares implement hooks that are called at specific points
    in the agent execution lifecycle.
    """

    async def before_agent_start(self, state: "ThreadState") -> None:
        """Called before the agent starts processing.

        Args:
            state: Current ThreadState (mutable).
        """
        pass

    async def after_agent_end(self, state: "ThreadState") -> None:
        """Called after the agent finishes processing.

        Args:
            state: Current ThreadState.
        """
        pass

    async def before_tool_call(self, state: "ThreadState", tool_name: str, tool_args: dict) -> None:
        """Called before a tool is executed.

        Args:
            state: Current ThreadState.
            tool_name: Name of the tool to be called.
            tool_args: Arguments to the tool.
        """
        pass

    async def after_tool_call(self, state: "ThreadState", tool_name: str, tool_args: dict, result: str) -> None:
        """Called after a tool finishes executing.

        Args:
            state: Current ThreadState.
            tool_name: Name of the tool that was called.
            tool_args: Arguments that were passed.
            result: Tool execution result (as string).
        """
        pass

    async def on_error(self, state: "ThreadState", error: Exception) -> None:
        """Called when an error occurs during execution.

        Args:
            state: Current ThreadState.
            error: The exception that was raised.
        """
        pass


class MiddlewareChain:
    """Chain of middlewares with ordered execution.

    Hooks are called in order for "before_*" and reverse order for "after_*".
    """

    def __init__(self, middlewares: list[Middleware]):
        """Initialize chain.

        Args:
            middlewares: Ordered list of middlewares.
        """
        self.middlewares = middlewares

    async def before_agent_start(self, state: "ThreadState") -> None:
        for m in self.middlewares:
            await m.before_agent_start(state)

    async def after_agent_end(self, state: "ThreadState") -> None:
        for m in reversed(self.middlewares):
            await m.after_agent_end(state)

    async def before_tool_call(self, state: "ThreadState", tool_name: str, tool_args: dict) -> None:
        for m in self.middlewares:
            await m.before_tool_call(state, tool_name, tool_args)

    async def after_tool_call(self, state: "ThreadState", tool_name: str, tool_args: dict, result: str) -> None:
        for m in reversed(self.middlewares):
            await m.after_tool_call(state, tool_name, tool_args, result)

    async def on_error(self, state: "ThreadState", error: Exception) -> None:
        for m in reversed(self.middlewares):
            await m.on_error(state, error)