"""SecurityMiddleware - validates paths and commands before tool execution.

Applies security checks to prevent:
- Path traversal attacks (/mnt/user-data/../etc/passwd)
- Dangerous commands (rm -rf /, fork bomb, etc)
- Access to sensitive system files
"""
import re
from typing import Literal

from harness.agent.state import ThreadState
from harness.sandbox.path import validate_path

from .base import Middleware

# Dangerous command patterns
DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    # Recursive force delete
    (r"rm\s+-rf\s+/", "Recursive delete of root directory"),
    (r"rm\s+-rf\s+\*", "Recursive delete of all files"),
    # Fork bomb
    (r":\(\)\{:\|:&\};:", "Fork bomb detected"),
    # Overwrite system files
    (r">\s*/etc/passwd", "Overwrite /etc/passwd"),
    (r">\s*/etc/shadow", "Overwrite /etc/shadow"),
    # Download and execute
    (r"curl.*\|.*bash", "Pipe curl to bash (Living off the land)"),
    (r"wget.*\|.*bash", "Pipe wget to bash (Living off the land)"),
    # Port scanning
    (r"nmap", "Network port scanner"),
    # Privilege escalation
    (r"chmod\s+4777", "Set UID bit"),
    (r"chmod\s+\+s", "Set SUID bit"),
]

# Blacklist of paths that tools should never access
BLACKLISTED_PATHS: list[str] = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/root/.ssh",
    "/home/*/.ssh",
]


class SecurityMiddleware(Middleware):
    """Validates tool inputs before execution.

    Security checks:
        1. Virtual path validation (no path traversal)
        2. Command pattern matching (no dangerous commands)
        3. Path blacklist checking
    """

    def __init__(self, strict: bool = True):
        """Initialize middleware.

        Args:
            strict: If True, reject dangerous commands.
                   If False, only warn but allow.
        """
        self.strict = strict

    async def before_tool_call(
        self, state: ThreadState, tool_name: str, tool_args: dict
    ) -> None:
        """Validate tool arguments before execution.

        Args:
            state: Current ThreadState.
            tool_name: Name of the tool to execute.
            tool_args: Arguments to the tool.

        Raises:
            SecurityError: If validation fails in strict mode.
        """
        # Check based on tool type
        if tool_name in ("ReadFile", "WriteFile"):
            await self._validate_file_tool(tool_args)
        elif tool_name == "BashCommand":
            await self._validate_bash_command(tool_args)

    async def _validate_file_tool(self, tool_args: dict) -> None:
        """Validate file tool arguments.

        Args:
            tool_args: Tool arguments containing file_path.

        Raises:
            SecurityError: If path is invalid or blacklisted.
        """
        file_path = tool_args.get("file_path", "")

        # Validate virtual path
        validated = validate_path(file_path)
        if validated is None:
            raise SecurityError(f"Invalid or dangerous path: {file_path}")

        # Check blacklist
        for blacklisted in BLACKLISTED_PATHS:
            if self._path_matches(file_path, blacklisted):
                raise SecurityError(f"Access to blacklisted path: {file_path}")

    async def _validate_bash_command(self, tool_args: dict) -> None:
        """Validate bash command arguments.

        Args:
            tool_args: Tool arguments containing command.

        Raises:
            SecurityError: If command contains dangerous patterns.
        """
        command = tool_args.get("command", "")

        # Check for dangerous patterns
        for pattern, description in DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                if self.strict:
                    raise SecurityError(f"Dangerous command detected: {description}")
                # In non-strict mode, just log (could add warning here)

    def _path_matches(self, path: str, pattern: str) -> bool:
        """Check if path matches a glob-like pattern.

        Args:
            path: Path to check.
            pattern: Pattern with optional * wildcard.

        Returns:
            True if path matches pattern.
        """
        if "*" in pattern:
            regex = pattern.replace("*", ".*")
            return bool(re.match(f"^{regex}$", path))
        return path.startswith(pattern)


class SecurityError(Exception):
    """Raised when a security check fails."""
    pass