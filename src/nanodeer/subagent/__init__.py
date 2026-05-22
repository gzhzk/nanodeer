"""Subagent module — coordinator-worker pattern for parallel task execution."""

from .coordinator import SubagentCoordinator
from .runner import format_result
from .types import WorkerStatus, WorkerTask, WorkerSpec

__all__ = [
    "SubagentCoordinator",
    "WorkerStatus",
    "WorkerTask",
    "WorkerSpec",
    "format_result",
    "set_executor",
    "get_executor",
]

_coordinator: SubagentCoordinator | None = None


def set_executor(coordinator: SubagentCoordinator) -> None:
    """Set the global SubagentCoordinator instance (called by factory)."""
    global _coordinator
    _coordinator = coordinator


def get_executor() -> SubagentCoordinator:
    """Get the global SubagentCoordinator instance."""
    if _coordinator is None:
        raise RuntimeError("SubagentCoordinator not initialized")
    return _coordinator
