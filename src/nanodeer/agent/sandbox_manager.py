"""Execution-only sandbox resources and lifecycle.

Replaces SandboxMiddleware (before_llm / after_tools_all hooks).
Provides idempotent acquire/release that reuses containers across turns
via the module-level _sandbox_context.

Used by the top-level agent_loop directly, not as middleware.
"""

import logging
from dataclasses import dataclass

from nanodeer.sandbox import (
    Sandbox,
    SandboxProvider,
    clear_sandbox,
    create_sandbox_provider,
    get_sandbox,
    set_sandbox,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResources:
    """Ephemeral resources for one run; never part of AgentState/checkpoint."""

    thread_id: str
    sandbox: Sandbox | None = None


class SandboxManager:
    """Container lifecycle: acquire (idempotent), release (idempotent)."""

    def __init__(self, provider: SandboxProvider | None = None):
        self._provider = provider or create_sandbox_provider()

    async def acquire(self, resources: ExecutionResources) -> Sandbox:
        """Ensure sandbox is available for this thread.

        Idempotent — if already acquired this turn or cached in module-level
        _sandbox_context, reuses without calling Docker again.
        """
        # Check module-level context (survives WAIT across turns)
        existing = get_sandbox(resources.thread_id)
        if existing:
            resources.sandbox = existing
            return existing

        if not resources.thread_id:
            raise ValueError("thread_id required to acquire sandbox")

        sandbox = await self._provider.acquire(resources.thread_id)
        resources.sandbox = sandbox
        set_sandbox(resources.thread_id, sandbox)
        return sandbox

    async def release(self, resources: ExecutionResources) -> None:
        """Release container. Idempotent — skips if already released."""
        sandbox = resources.sandbox
        if sandbox is None:
            return

        try:
            await self._provider.release(sandbox)
        except Exception:
            logger.exception("Error releasing sandbox %s", sandbox.exec_id)
        finally:
            clear_sandbox(resources.thread_id)
            resources.sandbox = None


__all__ = ["ExecutionResources", "SandboxManager"]
