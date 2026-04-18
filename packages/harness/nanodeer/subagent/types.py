"""Subagent type definitions."""

from enum import Enum


class SubagentType(str, Enum):
    """Type of subagent determining its capabilities."""

    GENERAL = "general"  # Full-featured subagent with all tools
    BASH = "bash"  # Bash-only subagent