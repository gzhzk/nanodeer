"""Tool group definitions for progressive tool exposure.

Default profile starts with only the "core" group available.
The agent can call request_tools() to unlock additional groups.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Group name → set of tool names
TOOL_GROUPS: dict[str, set[str]] = {
    "core": {"read_file", "write_file", "edit_file", "bash"},
    "file": {"ls", "glob", "grep"},
    "advanced": {
        "git",
        "exec_python",
        "web_search",
        "web_fetch",
        "read_image",
    },
    "memory": {"save_memory", "search_memory"},
    "plan": {"create_plan", "add_step", "update_step", "list_plans"},
    "subagent": {"spawn_subagent", "get_subagent_results"},
}

# Descriptions shown to the LLM via request_tools descriptions
GROUP_DESCRIPTIONS: dict[str, str] = {
    "core": "File editing and shell commands (always available).",
    "file": "File system exploration and search (ls, glob, grep).",
    "advanced": "Advanced operations: git, Python execution, web search.",
    "memory": "Persistent memory: save and recall across sessions.",
    "plan": "Task planning: create and manage multi-step plans.",
    "subagent": "Subagent orchestration: spawn workers for parallel tasks.",
}

# Group dependencies: unlocking a group also unlocks its dependencies
GROUP_DEPS: dict[str, list[str]] = {
    "advanced": ["file"],
}

# Group that is always active (cannot be revoked)
CORE_GROUP = "core"

AVAILABLE_GROUPS: set[str] = set(TOOL_GROUPS.keys())


def resolve_tools(groups: list[str]) -> set[str]:
    """Return the set of tool names from the given groups, including dependencies."""
    resolved: set[str] = set()
    seen: set[str] = set()
    queue = list(groups)
    while queue:
        g = queue.pop()
        if g in seen or g not in TOOL_GROUPS:
            continue
        seen.add(g)
        resolved.update(TOOL_GROUPS[g])
        queue.extend(GROUP_DEPS.get(g, []))
    return resolved


def validate_groups(groups: list[str]) -> tuple[list[str], list[str]]:
    """Validate requested groups. Returns (valid_group_names, invalid_group_names)."""
    valid, invalid = [], []
    for g in groups:
        if g in TOOL_GROUPS:
            valid.append(g)
        else:
            invalid.append(g)
    return valid, invalid


class RequestToolsInput(BaseModel):
    """Request additional tool groups to be unlocked."""

    groups: list[str] = Field(
        description="Names of tool groups to activate. "
        f"Available: {', '.join(sorted(AVAILABLE_GROUPS - {CORE_GROUP}))}."
        " Example: ['file', 'advanced']"
    )


REQUEST_TOOLS_TOOL_SCHEMA: dict[str, Any] = {
    "name": "request_tools",
    "description": "Request additional tool groups beyond the default core tools. "
    "Available groups: "
    + ", ".join(f"{k} ({v})" for k, v in sorted(GROUP_DESCRIPTIONS.items()) if k != CORE_GROUP),
    "parameters": RequestToolsInput.model_json_schema(),
}
