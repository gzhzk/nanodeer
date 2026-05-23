"""SandboxManager — container lifecycle management.

Replaces SandboxMiddleware (before_llm / after_tools_all hooks).
Provides idempotent acquire/release that reuses containers across turns
via the module-level _sandbox_context.

Used by ReActExecutor directly, not as middleware.
"""

import logging

from nanodeer.agent.state import SandboxState, ThreadState
from nanodeer.config import get_config
from nanodeer.sandbox import SandboxProvider, get_sandbox, set_sandbox, clear_sandbox
from nanodeer.sandbox.docker import DockerSandboxProvider
from nanodeer.sandbox.local import LocalSandboxProvider

logger = logging.getLogger(__name__)


class SandboxManager:
    """Container lifecycle: acquire (idempotent), release (idempotent)."""

    def __init__(self, provider: SandboxProvider | None = None):
        self._provider = provider or self._create_provider()

    @staticmethod
    def _create_provider() -> SandboxProvider:
        cfg = get_config()
        try:
            import docker
            docker.client.from_env().ping()
            return DockerSandboxProvider(
                image=cfg.sandbox.image,
                container_prefix=cfg.sandbox.container_prefix,
                network_mode=cfg.sandbox.network_mode,
                base_path=cfg.sandbox.base_path,
            )
        except Exception:
            logger.info("Docker unavailable, falling back to LocalSandboxProvider")
            return LocalSandboxProvider()

    async def acquire(self, state: ThreadState) -> None:
        """Ensure sandbox is available for this thread.

        Idempotent — if already acquired this turn or cached in module-level
        _sandbox_context, reuses without calling Docker again.
        """
        if state.sandbox is None:
            state.sandbox = SandboxState()
        if state.sandbox.container_id:
            return  # already acquired this turn

        # Check module-level context (survives WAIT across turns)
        existing = get_sandbox(state.thread_id)
        if existing:
            state.sandbox.exec_id = existing.exec_id
            state.sandbox.container_id = existing.container_id
            state.sandbox.working_dir = existing.working_dir
            state.sandbox.status = "ready"
            return

        if not state.thread_id:
            raise ValueError("thread_id required to acquire sandbox")

        sandbox = await self._provider.acquire(state.thread_id)
        state.sandbox.exec_id = sandbox.exec_id
        state.sandbox.container_id = sandbox.container_id
        state.sandbox.working_dir = sandbox.working_dir
        state.sandbox.status = "ready"
        set_sandbox(state.thread_id, sandbox)

    async def release(self, state: ThreadState) -> None:
        """Release container. Idempotent — skips if already released."""
        if not state.sandbox or state.sandbox.status == "released":
            return

        exec_id = state.sandbox.exec_id
        try:
            await self._provider.release(state.sandbox)
        except Exception:
            logger.exception("Error releasing sandbox %s", exec_id)
        finally:
            if exec_id:
                clear_sandbox(exec_id)
            state.sandbox.status = "released"
