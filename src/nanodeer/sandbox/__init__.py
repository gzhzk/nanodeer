"""Sandbox isolation layer - containerized execution for Agent tools.

Each thread gets its own sandbox (Docker container).
"""
import asyncio
import logging
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    stdout: str
    stderr: str
    returncode: int


@dataclass
class Sandbox:
    exec_id: str
    container_id: str
    working_dir: str


@dataclass
class SandboxCommand:
    cmd: str
    timeout: int = 30


class SandboxProvider(ABC):
    @abstractmethod
    async def acquire(self, exec_id: str) -> Sandbox: ...

    @abstractmethod
    async def release(self, sandbox: Sandbox) -> None: ...

    @abstractmethod
    async def run(self, sandbox: Sandbox, command: str, timeout: int = 30) -> RunResult: ...


class LazySandboxProvider(SandboxProvider):
    """Create the concrete execution backend only when a command needs it."""

    def __init__(self):
        self._provider: SandboxProvider | None = None
        self._lock = asyncio.Lock()

    async def _get_provider(self) -> SandboxProvider:
        if self._provider is not None:
            return self._provider
        async with self._lock:
            if self._provider is None:
                self._provider = _create_concrete_sandbox_provider()
        return self._provider

    async def acquire(self, exec_id: str) -> Sandbox:
        return await (await self._get_provider()).acquire(exec_id)

    async def release(self, sandbox: Sandbox) -> None:
        if self._provider is not None:
            await self._provider.release(sandbox)

    async def run(self, sandbox: Sandbox, command: str, timeout: int = 30) -> RunResult:
        return await (await self._get_provider()).run(sandbox, command, timeout)


# Execution lookup for sandbox-wrapped tools; never serialized into AgentState.
_sandbox_context: dict[str, Sandbox] = {}
_sandbox_lock = threading.Lock()


def set_sandbox(exec_id: str, sandbox: Sandbox) -> None:
    with _sandbox_lock:
        _sandbox_context[exec_id] = sandbox


def get_sandbox(exec_id: str) -> Sandbox | None:
    with _sandbox_lock:
        return _sandbox_context.get(exec_id)


def clear_sandbox(exec_id: str) -> None:
    with _sandbox_lock:
        _sandbox_context.pop(exec_id, None)


def resolve_virtual_path(virtual_path: str) -> str:
    """Resolve a path through the active thread Workspace (legacy helper)."""
    from nanodeer.workspace import resolve_workspace_path

    return str(resolve_workspace_path(virtual_path))


def _create_concrete_sandbox_provider() -> SandboxProvider:
    """Create an isolated backend; local host execution requires explicit opt-in."""
    from .local import LocalSandboxProvider
    from ..config import get_config

    cfg = get_config()
    try:
        from .docker import DockerSandboxProvider
        import docker
        docker.client.from_env().ping()
        return DockerSandboxProvider(
            image=cfg.sandbox.image,
            container_prefix=cfg.sandbox.container_prefix,
            network_mode=cfg.sandbox.network_mode,
            base_path=cfg.sandbox.base_path,
        )
    except Exception as exc:
        if os.getenv("NANODEER_ALLOW_LOCAL_EXECUTION", "").lower() in {
            "1", "true", "yes", "on",
        }:
            logger.warning("Docker unavailable; using explicitly enabled local execution")
            return LocalSandboxProvider()
        raise RuntimeError(
            "Docker sandbox is unavailable. Set NANODEER_ALLOW_LOCAL_EXECUTION=1 "
            "only for an explicitly trusted local environment."
        ) from exc


def create_sandbox_provider() -> SandboxProvider:
    """Return a provider that defers Docker probing until first command execution."""
    return LazySandboxProvider()
