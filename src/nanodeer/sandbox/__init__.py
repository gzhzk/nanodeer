"""Sandbox isolation layer - containerized execution for Agent tools.

Each thread gets its own sandbox (Docker container).
"""
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..agent.state import SandboxState


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
