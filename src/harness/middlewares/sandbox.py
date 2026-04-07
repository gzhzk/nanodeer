"""SandboxMiddleware - acquires/releases Docker sandbox per thread."""
from harness.agent.state import ThreadState
from harness.config import get_config
from harness.sandbox import SandboxProvider, set_sandbox_provider, clear_sandbox_provider
from harness.sandbox.docker import DockerSandboxProvider

from .base import Middleware


class SandboxMiddleware(Middleware):
    """Manages Docker sandbox lifecycle.

    before_agent_start: acquire container + register provider in context
    after_agent_end:    release container + clear context
    on_error:          release container (cleanup)
    """

    def __init__(self, provider: SandboxProvider | None = None):
        self.config = get_config()
        self.provider = provider or DockerSandboxProvider(
            image=self.config.sandbox.image,
            container_prefix=self.config.sandbox.container_prefix,
            network_mode=self.config.sandbox.network_mode,
        )

    async def before_agent_start(self, state: ThreadState) -> None:
        """Acquire sandbox container before agent starts."""
        if not state.thread_id:
            raise ValueError("SandboxMiddleware requires thread_id")

        sandbox = await self.provider.acquire(state.thread_id)

        state.sandbox.thread_id = state.thread_id
        state.sandbox.container_id = sandbox.container_id
        state.sandbox.working_dir = sandbox.working_dir
        state.sandbox.status = "ready"

        # Register provider in context (tool executor reads from here)
        set_sandbox_provider(state.thread_id, self.provider)

    async def after_agent_end(self, state: ThreadState) -> None:
        """Release sandbox container after agent finishes."""
        await self._release_if_needed(state)

    async def on_error(self, state: ThreadState, error: Exception) -> None:
        """Release sandbox on error (cleanup)."""
        await self._release_if_needed(state)

    async def _release_if_needed(self, state: ThreadState) -> None:
        """Release sandbox if acquired."""
        if not state.sandbox or not state.sandbox.container_id:
            return

        thread_id = state.sandbox.thread_id
        try:
            await self.provider.release(state.sandbox)
            state.sandbox.status = "released"
        except Exception:
            pass  # best effort
        finally:
            clear_sandbox_provider(thread_id)