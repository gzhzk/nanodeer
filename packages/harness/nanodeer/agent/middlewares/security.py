"""SecurityMiddleware - validates file paths before tool execution.

Uses the same error-handling pattern as other middlewares:
inject HumanMessage + strip tool_calls, no exceptions.
"""
import re

from langchain_core.messages import AIMessage, HumanMessage

from nanodeer.agent.state import ThreadState
from nanodeer.container.path import validate_path

from .base import Middleware

# Paths that tools should never access
BLACKLISTED_PATHS: list[str] = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/root/.ssh",
    "/home/*/.ssh",
]


class SecurityMiddleware(Middleware):
    """Validates file paths before tool execution.

    On invalid path: injects error HumanMessage and strips tool_calls.
    Bash command auditing is handled by SandboxMiddleware instead.
    """

    async def before_tool_call(
        self, state: ThreadState, tool_name: str, tool_args: dict
    ) -> None:
        """Validate file tool arguments."""
        if tool_name in ("read_file", "write_file", "ls", "glob", "grep"):
            await self._validate_file_tool(state, tool_args)

    async def _validate_file_tool(self, state: ThreadState, tool_args: dict) -> None:
        """Validate file path. On failure: inject error + strip tool_calls."""
        file_path = tool_args.get("file_path", "")

        validated = validate_path(file_path)
        if validated is None:
            self._inject_error(state, f"Invalid or dangerous path: {file_path}")
            return

        for blacklisted in BLACKLISTED_PATHS:
            if self._path_matches(file_path, blacklisted):
                self._inject_error(state, f"Access to blacklisted path: {file_path}")
                return

    def _inject_error(self, state: ThreadState, message: str) -> None:
        """Inject error HumanMessage and strip tool_calls to prevent execution."""
        if not hasattr(state, "messages"):
            return

        state.messages.append(HumanMessage(
            content=f"🚫 Security Error: {message}"
        ))

        for msg in reversed(state.messages):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                stripped = AIMessage(
                    content=msg.content,
                    tool_calls=[],  # type: ignore
                    id=msg.id,
                    name=msg.name,
                    usage_metadata=getattr(msg, "usage_metadata", None),
                )
                for i, m in enumerate(state.messages):
                    if m is msg:
                        state.messages[i] = stripped
                        break
                break

    def _path_matches(self, path: str, pattern: str) -> bool:
        """Check if path matches glob-like pattern."""
        if "*" in pattern:
            regex = pattern.replace("*", ".*")
            return bool(re.match(f"^{regex}$", path))
        return path.startswith(pattern)
