"""Subagents module - lightweight parallel task execution."""

from .runner import run_subagent, run_subagents_in_parallel, generate_subagent_id
from .types import SubagentType

__all__ = [
    "run_subagent",
    "run_subagents_in_parallel",
    "generate_subagent_id",
    "SubagentType",
]
