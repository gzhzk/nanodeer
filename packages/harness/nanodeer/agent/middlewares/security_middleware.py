"""SecurityMiddleware — validates file paths before tool execution.

Sets next_action="end" on violation, causing the graph to route to END.
Does NOT inject HumanMessages or strip tool_calls — pure signal-based interrupt.
"""
import re

from nanodeer.agent.state import ThreadState
from nanodeer.container.path import validate_path

from .base import Middleware

BLACKLISTED_PATHS: list[str] = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/root/.ssh",
    "/home/*/.ssh",
]


class SecurityMiddleware(Middleware):
    """Validates file paths before tool execution.

    On invalid path: sets next_action="end" to directly interrupt the graph.
    Does NOT inject HumanMessages or strip tool_calls — pure signal-based.
    """

    async def before_tools(
        self, state: ThreadState, tool_name: str, tool_args: dict
    ) -> None:
        """Validate file tool arguments."""
        if tool_name in ("read_file", "write_file", "ls", "glob", "grep"):
            await self._validate_file_tool(state, tool_args)

    async def _validate_file_tool(self, state: ThreadState, tool_args: dict) -> None:
        """Validate file path. On failure: set next_action="end"."""
        file_path = tool_args.get("file_path", "")

        validated = validate_path(file_path)
        if validated is None:
            state.next_action = "end"
            return

        for blacklisted in BLACKLISTED_PATHS:
            if self._path_matches(file_path, blacklisted):
                state.next_action = "end"
                return

    def _path_matches(self, path: str, pattern: str) -> bool:
        """Check if path matches glob-like pattern."""
        if "*" in pattern:
            regex = pattern.replace("*", ".*")
            return bool(re.match(f"^{regex}$", path))
        return path.startswith(pattern)