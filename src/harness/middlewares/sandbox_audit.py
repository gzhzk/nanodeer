"""SandboxAuditMiddleware — classifies and guards bash commands.

Intercepts `bash` tool calls and classifies commands by risk level:
- HIGH_RISK: block immediately, strip tool_calls, inject error message
- MEDIUM_RISK: warn but allow

Reference: DeerFlow SandboxAuditMiddleware.
"""

import logging
import re
import shlex
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from ..agent.state import ThreadState
from .base import Middleware

logger = logging.getLogger(__name__)


# Risk-level command patterns
_HIGH_RISK_PATTERNS: list[re.Pattern] = [
    # Destructive overrides
    re.compile(r"^\s*>\s*/etc/passwd", re.IGNORECASE),
    re.compile(r"^\s*>\s*/etc/shadow", re.IGNORECASE),
    re.compile(r"^\s*>\s*/etc/sudoers"),
    # Recursive delete from root
    re.compile(r"rm\s+-rf\s+/\s*(--.*)?$", re.IGNORECASE),
    re.compile(r"rm\s+-rf\s+/\*\s*$", re.IGNORECASE),
    # Fork bomb
    re.compile(r":\(\)\s*\{\s*\|\s*:\s*&\s*\}\s*;", re.IGNORECASE),
    # Pipe download to shell
    re.compile(r"(curl|wget).*\|\s*(bash|sh)", re.IGNORECASE),
    # Direct write to sensitive files
    re.compile(r"dd\s+if=", re.IGNORECASE),
    re.compile(r"mkfs", re.IGNORECASE),
    # Read sensitive files
    re.compile(r"cat\s+/etc/shadow"),
    re.compile(r"cat\s+/etc/sudoers"),
    # Set dangerous permissions
    re.compile(r"chmod\s+4777", re.IGNORECASE),
    # Download and execute
    re.compile(r"(curl|wget).*-O.*\|\s*bash", re.IGNORECASE),
]

_MEDIUM_RISK_PATTERNS: list[re.Pattern] = [
    # Overly permissive permissions
    re.compile(r"chmod\s+777\b", re.IGNORECASE),
    re.compile(r"chmod\s+000\b", re.IGNORECASE),
    re.compile(r"chmod\s+\+w\s+/etc", re.IGNORECASE),
    # Package installation (can modify system)
    re.compile(r"\bpip\s+install\b", re.IGNORECASE),
    re.compile(r"\bapt-get\s+install\b", re.IGNORECASE),
    re.compile(r"\bapt\s+install\b", re.IGNORECASE),
    re.compile(r"\byum\s+install\b", re.IGNORECASE),
    re.compile(r"\bdnf\s+install\b", re.IGNORECASE),
    re.compile(r"\bpnpm\s+add\b", re.IGNORECASE),
    re.compile(r"\bnpm\s+install\b", re.IGNORECASE),
    re.compile(r"\byarn\s+add\b", re.IGNORECASE),
    # Network scanners
    re.compile(r"\bnmap\b", re.IGNORECASE),
    # Forkbomb variants
    re.compile(r":\(|:{:|:&"),
]


class SandboxAuditMiddleware(Middleware):
    """Audits `bash` tool calls for dangerous commands.

    Risk levels:
    - HIGH: immediately block, strip tool_calls, inject error
    - MEDIUM: warn but allow execution
    - LOW: allowed

    Commands are parsed with shlex to avoid false positives from
    quoted strings containing dangerous-looking substrings.
    """

    async def before_tool_call(
        self, state: ThreadState, tool_name: str, tool_args: dict
    ) -> None:
        """Audit the command before execution."""
        if tool_name != "bash":
            return

        command = tool_args.get("command", "")
        if not command:
            return

        risk, detail = self._classify(command)
        thread_id = getattr(state, "thread_id", None) or "default"

        if risk == "HIGH":
            logger.warning(
                f"SandboxAudit: HIGH_RISK blocked for thread={thread_id} "
                f"command={command[:80]!r} detail={detail}"
            )
            self._inject_error(state, command, detail)
        elif risk == "MEDIUM":
            logger.warning(
                f"SandboxAudit: MEDIUM_RISK warning for thread={thread_id} "
                f"command={command[:80]!r} detail={detail}"
            )
            self._inject_warning(state, command, detail)

    def _classify(self, command: str) -> tuple[str, str]:
        """Classify a bash command by risk level.

        Args:
            command: Raw command string.

        Returns:
            Tuple of (risk_level, detail). risk_level is "HIGH", "MEDIUM", or "LOW".
        """
        # Try to extract the first token for basic pattern matching
        try:
            tokens = shlex.split(command)
        except ValueError:
            # Unclosed quote — still scan the raw string
            tokens = [command]

        first_cmd = tokens[0] if tokens else ""

        # HIGH risk: scan full command
        for pattern in _HIGH_RISK_PATTERNS:
            if pattern.search(command):
                return "HIGH", pattern.pattern

        # MEDIUM risk: check first token or full command
        medium_cmd_patterns = [
            r"\bnmap\b",
            r":\(|:{:|::&",
            r"\bpip\s+install\b",
            r"\bapt-get\s+install\b",
            r"\bapt\s+install\b",
            r"\byum\s+install\b",
            r"\bdnf\s+install\b",
            r"\bnpm\s+install\b",
            r"\bpnpm\s+add\b",
            r"\byarn\s+add\b",
        ]

        for pattern in _MEDIUM_RISK_PATTERNS:
            if pattern.search(command):
                return "MEDIUM", pattern.pattern

        return "LOW", ""

    def _inject_error(self, state: ThreadState, command: str, detail: str) -> None:
        """Inject error into state and strip tool_calls to prevent execution."""
        error_msg = (
            f"🚫 Command blocked by security policy:\n"
            f"  The following command was blocked because it matches a high-risk pattern:\n"
            f"  Pattern: {detail}\n"
            f"  Command: {command[:200]}\n"
            f"  If you believe this is a false positive, please contact your administrator."
        )
        self._inject_message(state, error_msg, is_error=True)

    def _inject_warning(self, state: ThreadState, command: str, detail: str) -> None:
        """Inject warning into state but allow execution to continue."""
        warning = (
            f"⚠️ Warning: medium-risk command detected.\n"
            f"  Pattern: {detail}\n"
            f"  Command: {command[:200]}\n"
            f"  This command will be executed but may have side effects."
        )
        self._inject_message(state, warning, is_error=False)

    def _inject_message(
        self, state: ThreadState, content: str, *, is_error: bool
    ) -> None:
        """Inject a HumanMessage into state.messages and strip tool_calls from last AIMessage."""
        if not hasattr(state, "messages"):
            return

        # Inject message before stripping so LLM sees it
        state.messages.append(HumanMessage(content=content))

        # Strip tool_calls from the last AIMessage to prevent execution
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
