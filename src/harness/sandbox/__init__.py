"""Sandbox isolation layer.

Provides containerized execution environment for Agent tools.
NanoDeer only uses Docker containers (no Local fallback).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RunResult:
    """Result of a command execution inside sandbox."""
    stdout: str
    stderr: str
    returncode: int


@dataclass
class Sandbox:
    """Represents a sandboxed execution environment.

    Attributes:
        thread_id: Unique identifier for the thread.
        container_id: Docker container ID.
        working_dir: Physical working directory path inside the container.
    """
    thread_id: str
    container_id: str
    working_dir: str


class SandboxProvider(ABC):
    """Abstract base class for sandbox providers.

    Each thread gets its own sandbox instance (container).
    Sandboxes are acquired before use and released when done.
    """

    @abstractmethod
    async def acquire(self, thread_id: str) -> Sandbox:
        """Create/acquire a sandbox instance for the given thread.

        Args:
            thread_id: Unique identifier for the thread.

        Returns:
            Sandbox instance ready for command execution.
        """

    @abstractmethod
    async def release(self, sandbox: Sandbox) -> None:
        """Release/destroy a sandbox instance.

        Args:
            sandbox: Sandbox instance to release.
        """

    @abstractmethod
    async def run(self, sandbox: Sandbox, command: str) -> RunResult:
        """Execute a command inside the sandbox.

        Args:
            sandbox: Sandbox instance to execute in.
            command: Command string to execute.

        Returns:
            RunResult with stdout, stderr, and returncode.
        """


# Module-level sandbox context for sharing provider across components
# Set by SandboxMiddleware.before_agent_start, read by builder's tool executor
_sandbox_context: dict[str, "SandboxProvider"] = {}


def set_sandbox_provider(thread_id: str, provider: SandboxProvider) -> None:
    """Set the sandbox provider for a thread.

    Args:
        thread_id: Thread identifier.
        provider: SandboxProvider instance (lives for duration of thread).
    """
    _sandbox_context[thread_id] = provider


def get_sandbox_provider(thread_id: str) -> "SandboxProvider | None":
    """Get the sandbox provider for a thread.

    Args:
        thread_id: Thread identifier.

    Returns:
        SandboxProvider instance or None if not set.
    """
    return _sandbox_context.get(thread_id)


def clear_sandbox_provider(thread_id: str) -> None:
    """Remove sandbox provider for a thread (called after release).

    Args:
        thread_id: Thread identifier.
    """
    _sandbox_context.pop(thread_id, None)