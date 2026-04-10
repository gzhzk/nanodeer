"""SandboxMiddleware - manages container lifecycle and audits bash commands.

Merged from SandboxMiddleware + SandboxAuditMiddleware.
- before_agent_start: acquire container + register provider in context
- before_tool_call: audit bash commands for dangerous patterns
- after_agent_end: release container + clear context
- on_error: release container (cleanup)
"""
import logging
import re
import shlex

from langchain_core.messages import AIMessage, HumanMessage

from nanodeer.agent.state import ThreadState
from nanodeer.config import get_config
from nanodeer.container import SandboxProvider, set_sandbox_provider, clear_sandbox_provider
from nanodeer.container.docker import DockerSandboxProvider

from .base import Middleware

logger = logging.getLogger(__name__)

# Risk-level command patterns (from merged SandboxAuditMiddleware)
_HIGH_RISK_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*>\s*/etc/passwd", re.IGNORECASE),
    re.compile(r"^\s*>\s*/etc/shadow", re.IGNORECASE),
    re.compile(r"^\s*>\s*/etc/sudoers"),
    re.compile(r"rm\s+-rf\s+/\s*(--.*)?$", re.IGNORECASE),
    re.compile(r"rm\s+-rf\s+/\*\s*$", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*\|\s*:\s*&\s*\}\s*;", re.IGNORECASE),
    re.compile(r"(curl|wget).*\|\s*(bash|sh)", re.IGNORECASE),
    re.compile(r"dd\s+if=", re.IGNORECASE),
    re.compile(r"mkfs", re.IGNORECASE),
    re.compile(r"cat\s+/etc/shadow"),
    re.compile(r"cat\s+/etc/sudoers"),
    re.compile(r"chmod\s+4777", re.IGNORECASE),
    re.compile(r"(curl|wget).*-O.*\|\s*bash", re.IGNORECASE),
]

_MEDIUM_RISK_PATTERNS: list[re.Pattern] = [
    re.compile(r"chmod\s+777\b", re.IGNORECASE),
    re.compile(r"chmod\s+000\b", re.IGNORECASE),
    re.compile(r"chmod\s+\+w\s+/etc", re.IGNORECASE),
    re.compile(r"\bpip\s+install\b", re.IGNORECASE),
    re.compile(r"\bapt-get\s+install\b", re.IGNORECASE),
    re.compile(r"\bapt\s+install\b", re.IGNORECASE),
    re.compile(r"\byum\s+install\b", re.IGNORECASE),
    re.compile(r"\bdnf\s+install\b", re.IGNORECASE),
    re.compile(r"\bnpm\s+install\b", re.IGNORECASE),
    re.compile(r"\bpnpm\s+add\b", re.IGNORECASE),
    re.compile(r"\byarn\s+add\b", re.IGNORECASE),
    re.compile(r"\bnmap\b", re.IGNORECASE),
    re.compile(r":\(|:{:|:&"),
]


class SandboxMiddleware(Middleware):
    """Manages Docker sandbox lifecycle + audits bash commands.

    - before_agent_start: acquire container + register provider
    - before_tool_call: audit bash commands for dangerous patterns
    - after_agent_end: release container + clear context
    - on_error: release container (cleanup)
    """

    def __init__(self, provider: SandboxProvider | None = None):
        self.config = get_config()
        self.provider = provider or DockerSandboxProvider(
            image=self.config.sandbox.image,
            container_prefix=self.config.sandbox.container_prefix,
            network_mode=self.config.sandbox.network_mode,
        )

    async def before_agent_start(self, state: ThreadState) -> None:
        """Acquire sandbox container before agent starts."""
        if not state.thread_id:
            raise ValueError("SandboxMiddleware requires thread_id")

        sandbox = await self.provider.acquire(state.thread_id)

        state.sandbox.thread_id = state.thread_id
        state.sandbox.container_id = sandbox.container_id
        state.sandbox.working_dir = sandbox.working_dir
        state.sandbox.status = "ready"

        set_sandbox_provider(state.thread_id, self.provider)

    async def before_tool_call(
        self, state: ThreadState, tool_name: str, tool_args: dict
    ) -> None:
        """Audit bash commands for dangerous patterns before execution."""
        if tool_name != "bash":
            return

        command = tool_args.get("command", "")
        if not command:
            return

        risk, detail = self._classify(command)
        thread_id = getattr(state, "thread_id", None) or "default"

        if risk == "HIGH":
            logger.warning(
                f"SandboxMiddleware: HIGH_RISK blocked thread={thread_id} "
                f"command={command[:80]!r}"
            )
            self._inject_error(state, command, detail)
        elif risk == "MEDIUM":
            logger.warning(
                f"SandboxMiddleware: MEDIUM_RISK warning thread={thread_id} "
                f"command={command[:80]!r}"
            )
            self._inject_warning(state, command, detail)

    def _classify(self, command: str) -> tuple[str, str]:
        """Classify bash command risk level. Returns (HIGH|MEDIUM|LOW, detail)."""
        try:
            tokens = shlex.split(command)
        except ValueError:
            tokens = [command]

        for pattern in _HIGH_RISK_PATTERNS:
            if pattern.search(command):
                return "HIGH", pattern.pattern

        for pattern in _MEDIUM_RISK_PATTERNS:
            if pattern.search(command):
                return "MEDIUM", pattern.pattern

        return "LOW", ""

    def _inject_error(self, state: ThreadState, command: str, detail: str) -> None:
        """Inject error and strip tool_calls to prevent execution."""
        error_msg = (
            f"🚫 Command blocked by security policy:\n"
            f"  Pattern: {detail}\n"
            f"  Command: {command[:200]}\n"
            f"  If you believe this is a false positive, contact your administrator."
        )
        self._inject_message(state, error_msg, is_error=True)

    def _inject_warning(self, state: ThreadState, command: str, detail: str) -> None:
        """Inject warning but allow execution to continue."""
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
        """Inject HumanMessage and strip tool_calls from last AIMessage."""
        if not hasattr(state, "messages"):
            return

        state.messages.append(HumanMessage(content=content))

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

    async def after_agent_end(self, state: ThreadState) -> None:
        """Release sandbox container after agent finishes."""
        await self._release_if_needed(state)

    async def on_error(self, state: ThreadState, error: Exception) -> None:
        """Release sandbox on error (cleanup)."""
        await self._release_if_needed(state)

    async def _release_if_needed(self, state: ThreadState) -> None:
        """Release sandbox if acquired."""
        if not state.sandbox or not state.sandbox.container_id:
            return

        thread_id = state.sandbox.thread_id
        try:
            await self.provider.release(state.sandbox)
            state.sandbox.status = "released"
        except Exception:
            pass  # best effort
        finally:
            clear_sandbox_provider(thread_id)
