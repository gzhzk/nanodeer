"""Sandbox isolation layer - containerized execution for Agent tools.

Each thread gets its own sandbox (Docker container). Sandboxes are acquired
before use and released when done. Provider is stored in module-level context
(because it can't be serialized into ThreadState).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Protocol


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


@dataclass
class SandboxCommand:
    """Command to execute inside a sandbox container."""
    cmd: str
    timeout: int = 30
    env: dict[str, str] | None = None


class SandboxTool(Protocol):
    """Protocol for tools that can execute inside a sandbox.

    Tools that need sandbox isolation (file operations, shell, etc.)
    should implement this interface to provide their sandbox command.

    The agent builder checks if a tool implements this protocol,
    and if so, calls get_sandbox_command() to get the command to
    run inside the Docker container instead of executing locally.
    """

    @property
    def name(self) -> str:
        """Tool name."""

    def get_sandbox_command(self, args: dict, thread_id: str) -> SandboxCommand | None:
        """Get the command to execute in sandbox.

        Args:
            args: Tool arguments from the LLM tool call.
            thread_id: Thread ID for path translation.

        Returns:
            SandboxCommand to execute, or None if this tool should
            be executed locally (not in sandbox).
        """


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


# ---------------------------------------------------------------------------
# SandboxInfo — agent-level handle stored in ThreadState
# ---------------------------------------------------------------------------
# Moved from agent/state.py — SandboxInfo is a handle (not a Sandbox instance),
# describing the sandbox context for a thread. The actual Sandbox object lives
# in the sandbox/ layer and is managed by SandboxMiddleware.
# ---------------------------------------------------------------------------
from pydantic import BaseModel, Field


class SandboxInfo(BaseModel):
    """Sandbox execution context for a thread.

    This is stored in ThreadState so the agent graph knows whether a sandbox
    has been acquired and what container to use. The actual container
    lifecycle is managed by SandboxMiddleware via SandboxProvider.
    """
    thread_id: str
    container_id: str | None = None  # Filled after container is created
    status: Literal["acquiring", "ready", "released"] = "acquiring"
    working_dir: str | None = None  # Physical path inside container
