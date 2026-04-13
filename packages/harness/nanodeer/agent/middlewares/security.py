"""SecurityMiddleware — validates paths and bash commands before tool execution.

On violation: sets next_action="end" to directly interrupt the graph.
Pure signal-based, no message injection.
"""
import re

from nanodeer.agent.state import ThreadState
from nanodeer.sandbox.path import validate_path

from .base import Middleware

BLACKLISTED_PATHS = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/root/.ssh",
    "/home/*/.ssh",
]

# Dangerous shell patterns that should be blocked in bash commands
DANGEROUS_SHELL_CHARS = [";", "&&", "||", "|", ">", ">>", "<", "``", "$("]


class SecurityMiddleware(Middleware):
    """Validates paths and commands before tool execution."""

    async def before_tools(
        self, state: ThreadState, tool_name: str, tool_args: dict
    ) -> None:
        # File operations
        if tool_name in ("read_file", "write_file", "ls", "glob", "grep", "edit_file"):
            self._validate_file_path(state, tool_args)

        # Git operations
        elif tool_name == "git":
            self._validate_git_path(state, tool_args)

        # Bash commands
        elif tool_name == "bash":
            self._validate_bash_command(state, tool_args)

    def _validate_file_path(self, state: ThreadState, tool_args: dict) -> None:
        path = tool_args.get("file_path", "")
        if not path:
            return

        if validate_path(path) is None:
            state.next_action = "end"
            return

        for blocked in BLACKLISTED_PATHS:
            if self._path_matches(path, blocked):
                state.next_action = "end"
                return

    def _validate_git_path(self, state: ThreadState, tool_args: dict) -> None:
        path = tool_args.get("path", "")
        if not path:
            return

        # Normalize relative paths
        if not path.startswith("/mnt/user-data/"):
            path = "/mnt/user-data/workspace"

        if validate_path(path) is None:
            state.next_action = "end"
            return

    def _validate_bash_command(self, state: ThreadState, tool_args: dict) -> None:
        cmd = tool_args.get("command", "")
        if not cmd:
            return

        # Block dangerous shell characters
        for char in DANGEROUS_SHELL_CHARS:
            if char in cmd:
                state.next_action = "end"
                return

        # Block dangerous patterns
        dangerous = [
            r"^\s*rm\s+-rf\s+/\s*(--.*)?$",
            r"^\s*>\s*/etc/",
            r":\(\)\s*\{\s*\|\s*:\s*&\s*\}\s*;",
        ]
        for pattern in dangerous:
            if re.search(pattern, cmd):
                state.next_action = "end"
                return

    def _path_matches(self, path: str, pattern: str) -> bool:
        if "*" in pattern:
            regex = pattern.replace("*", ".*")
            return bool(re.match(f"^{regex}$", path))
        return path.startswith(pattern)
