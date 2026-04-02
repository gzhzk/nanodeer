"""SandboxMiddleware - acquires/releases Docker sandbox per thread.

Ensures each thread has an isolated sandbox container for tool execution.
Container is acquired before agent starts and released when done.
"""
from harness.agent.state import ThreadState
from harness.config import get_config
from harness.sandbox import SandboxProvider, set_sandbox_provider, clear_sandbox_provider
from harness.sandbox.docker import DockerSandboxProvider

from .base import Middleware


class SandboxMiddleware(Middleware):
    """Manages Docker sandbox lifecycle for agent execution.

    Flow:
        before_agent_start: acquire container + register provider in context
        after_agent_end:    release container + clear context
        on_error:          release container (cleanup)
    """

    def __init__(self, provider: SandboxProvider | None = None):
        """Initialize middleware.

        Args:
            provider: SandboxProvider instance. If None, creates DockerSandboxProvider.
        """
        self.config = get_config()
        self.provider = provider or DockerSandboxProvider(
            image=self.config.sandbox.image,
            container_prefix=self.config.sandbox.container_prefix,
        )

    async def before_agent_start(self, state: ThreadState) -> None:
        """Acquire sandbox container before agent starts.

        Args:
            state: ThreadState (must have thread_id set).
        """
        if not state.thread_id:
            raise ValueError("SandboxMiddleware requires thread_id in state")

        sandbox = await self.provider.acquire(state.thread_id)

        # Update sandbox info in state
        state.sandbox.thread_id = state.thread_id
        state.sandbox.container_id = sandbox.container_id
        state.sandbox.working_dir = sandbox.working_dir
        state.sandbox.status = "ready"

        # Register provider in context so tool executor can use it
        set_sandbox_provider(state.thread_id, self.provider)

    async def after_agent_end(self, state: ThreadState) -> None:
        """Release sandbox container after agent finishes.

        Args:
            state: ThreadState with sandbox info.
        """
        await self._release_if_needed(state)

    async def on_error(self, state: ThreadState, error: Exception) -> None:
        """Release sandbox on error (cleanup).

        Args:
            state: ThreadState with sandbox info.
            error: Exception that was raised.
        """
        await self._release_if_needed(state)

    async def _release_if_needed(self, state: ThreadState) -> None:
        """Release sandbox if it was acquired.

        Args:
            state: ThreadState with sandbox info.
        """
        if not state.sandbox or not state.sandbox.container_id:
            return

        thread_id = state.sandbox.thread_id
        try:
            await self.provider.release(state.sandbox)
            state.sandbox.status = "released"
        except Exception:
            # Best effort release - don't raise
            pass
        finally:
            # Always clear provider from context
            clear_sandbox_provider(thread_id)