"""Sandbox isolation layer - containerized execution for Agent tools.

Each thread gets its own sandbox (Docker container).
"""
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..agent.state import SandboxState

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


# Module-level context (can't serialize Sandbox into ThreadState)
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
    """Resolve /mnt/user-data/ paths to real host filesystem paths.

    File tools (read_file/write_file/edit_file) run on the host. The sandbox
    uses virtual paths like /mnt/user-data/workspace/ for consistency between
    host and container. This function translates those virtual paths to the
    actual host working directory of the active sandbox.

    Without an active sandbox, falls back to ~/.nanodeer/threads/default/user-data/.
    """
    if not virtual_path.startswith("/mnt/user-data"):
        return virtual_path

    rel = virtual_path.removeprefix("/mnt/user-data")

    # Check active sandbox for the real host path
    for _sid, sb in list(_sandbox_context.items()):
        wd = sb.working_dir.rstrip("/")
        return f"{wd}{rel}"

    # No sandbox active — use a reasonable default
    from pathlib import Path
    base = Path.home() / ".nanodeer" / "threads" / "default" / "user-data"
    result = str(base) + rel
    base.mkdir(parents=True, exist_ok=True)  # ensures the directory tree exists
    return result


def create_sandbox_provider() -> SandboxProvider:
    """Try Docker sandbox, fall back to LocalSandboxProvider on failure."""
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
    except Exception:
        logger.info("Docker unavailable, falling back to LocalSandboxProvider")
        return LocalSandboxProvider()
