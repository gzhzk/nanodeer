"""Subagents module - lightweight parallel task execution."""

from .runner import run_subagent, run_subagents_in_parallel, generate_subagent_id, SubagentRunner
from .types import SubagentType

__all__ = [
    "run_subagent",
    "run_subagents_in_parallel",
    "generate_subagent_id",
    "SubagentType",
    "SubagentRunner",
    "set_runner",
    "get_runner",
]

_runner: SubagentRunner | None = None


def set_runner(runner: SubagentRunner) -> None:
    """Set the global SubagentRunner instance (called by factory)."""
    global _runner
    _runner = runner


def get_runner() -> SubagentRunner:
    """Get the global SubagentRunner instance."""
    if _runner is None:
        raise RuntimeError("SubagentRunner not initialized")
    return _runner
