"""Sandbox isolation layer - containerized execution for Agent tools.

Each thread gets its own sandbox (Docker container). Sandboxes are acquired
before use and released when done. Provider is stored in module-level context
(because it can't be serialized into ThreadState).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RunResult:
    """Command execution result."""
    stdout: str
    stderr: str
    returncode: int


@dataclass
class Sandbox:
    """Sandboxed execution environment (always Docker container)."""
    thread_id: str
    container_id: str
    working_dir: str


class SandboxProvider(ABC):
    """Each thread gets its own sandbox instance. Acquired before use, released when done."""

    @abstractmethod
    async def acquire(self, thread_id: str) -> Sandbox:
        """Create sandbox instance for thread."""

    @abstractmethod
    async def release(self, sandbox: Sandbox) -> None:
        """Release/destroy sandbox instance."""

    @abstractmethod
    async def run(self, sandbox: Sandbox, command: str) -> RunResult:
        """Execute command inside sandbox."""


# Provider can't be serialized into ThreadState, so we use module-level context
_sandbox_context: dict[str, "SandboxProvider"] = {}


def set_sandbox_provider(thread_id: str, provider: SandboxProvider) -> None:
    """Set sandbox provider for a thread. Written by SandboxMiddleware, read by AgentBuilder."""
    _sandbox_context[thread_id] = provider


def get_sandbox_provider(thread_id: str) -> "SandboxProvider | None":
    """Get sandbox provider for a thread."""
    return _sandbox_context.get(thread_id)


def clear_sandbox_provider(thread_id: str) -> None:
    """Remove sandbox provider for a thread."""
    _sandbox_context.pop(thread_id, None)
