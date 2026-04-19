"""Subagent module - lightweight parallel task execution."""

from .runner import SubagentExecutor, run_many, format_result

__all__ = [
    "SubagentExecutor",
    "run_many",
    "format_result",
    "set_executor",
    "get_executor",
]

_executor: SubagentExecutor | None = None


def set_executor(executor: SubagentExecutor) -> None:
    """Set the global SubagentExecutor instance (called by factory)."""
    global _executor
    _executor = executor


def get_executor() -> SubagentExecutor:
    """Get the global SubagentExecutor instance."""
    if _executor is None:
        raise RuntimeError("SubagentExecutor not initialized")
    return _executor
