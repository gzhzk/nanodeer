"""SecurityMiddleware - validates paths and commands before tool execution."""
import re

from harness.agent.state import ThreadState
from harness.sandbox.path import validate_path

from .base import Middleware

# Dangerous command patterns (regex, description)
DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"rm\s+-rf\s+/", "Recursive delete of root"),
    (r"rm\s+-rf\s+\*", "Recursive delete all"),
    (r":\(\)\{:\|:&\};:", "Fork bomb"),
    (r">\s*/etc/passwd", "Overwrite /etc/passwd"),
    (r">\s*/etc/shadow", "Overwrite /etc/shadow"),
    (r"curl.*\|.*bash", "Pipe curl to bash"),
    (r"wget.*\|.*bash", "Pipe wget to bash"),
    (r"nmap", "Port scanner"),
    (r"chmod\s+4777", "Set UID bit"),
    (r"chmod\s+\+s", "Set SUID bit"),
]

# Paths that tools should never access
BLACKLISTED_PATHS: list[str] = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/root/.ssh",
    "/home/*/.ssh",
]


class SecurityMiddleware(Middleware):
    """Validates tool inputs before execution (path traversal, dangerous commands)."""

    def __init__(self, strict: bool = True):
        self.strict = strict

    async def before_tool_call(
        self, state: ThreadState, tool_name: str, tool_args: dict
    ) -> None:
        """Validate tool arguments."""
        # All file tools operate on virtual paths - validate them all
        if tool_name in ("read_file", "write_file", "ls", "glob", "grep"):
            await self._validate_file_tool(tool_args)

    async def _validate_file_tool(self, tool_args: dict) -> None:
        """Validate file path."""
        file_path = tool_args.get("file_path", "")

        validated = validate_path(file_path)
        if validated is None:
            raise SecurityError(f"Invalid or dangerous path: {file_path}")

        for blacklisted in BLACKLISTED_PATHS:
            if self._path_matches(file_path, blacklisted):
                raise SecurityError(f"Access to blacklisted path: {file_path}")

    async def _validate_bash_command(self, tool_args: dict) -> None:
        """Validate bash command. Raises in strict mode, silently allows in non-strict."""
        command = tool_args.get("command", "")

        for pattern, description in DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                if self.strict:
                    raise SecurityError(f"Dangerous command: {description}")
                # Non-strict: silently allow (useful for testing)

    def _path_matches(self, path: str, pattern: str) -> bool:
        """Check if path matches glob-like pattern."""
        if "*" in pattern:
            regex = pattern.replace("*", ".*")
            return bool(re.match(f"^{regex}$", path))
        return path.startswith(pattern)


class SecurityError(Exception):
    """Raised when a security check fails."""
    pass