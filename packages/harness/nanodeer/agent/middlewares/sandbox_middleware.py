"""SandboxMiddleware - manages container lifecycle and audits bash commands.

- before_llm: acquire container once (skip if already acquired)
- before_tools: audit bash commands for dangerous patterns
- after_tools_all: atomic release (regardless of tool success/failure)
"""
import logging
import re
import shlex

from nanodeer.agent.state import ThreadState
from nanodeer.config import get_config
from nanodeer.container import SandboxProvider, set_sandbox_provider, clear_sandbox_provider
from nanodeer.container.docker import DockerSandboxProvider

from .base import Middleware

logger = logging.getLogger(__name__)

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
    re.compile(r"chmod\s+000\b", re.IGNORECASE),
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

    - before_llm: acquire container once (skip if already acquired)
    - before_tools: audit bash commands for dangerous patterns
    - after_tools_all: atomic release
    """

    def __init__(self, provider: SandboxProvider | None = None):
        self.config = get_config()
        self.provider = provider or DockerSandboxProvider(
            image=self.config.sandbox.image,
            container_prefix=self.config.sandbox.container_prefix,
            network_mode=self.config.sandbox.network_mode,
        )

    async def before_llm(self, state: ThreadState) -> None:
        """Acquire sandbox container (only once)."""
        if state.sandbox and state.sandbox.container_id:
            return  # already acquired

        if not state.thread_data or not state.thread_data.thread_id:
            raise ValueError("SandboxMiddleware requires thread_data with thread_id")

        sandbox = await self.provider.acquire(state.thread_data.thread_id)

        state.sandbox.thread_id = state.thread_data.thread_id
        state.sandbox.container_id = sandbox.container_id
        state.sandbox.working_dir = sandbox.working_dir
        state.sandbox.status = "ready"

        set_sandbox_provider(state.thread_data.thread_id, self.provider)

    async def before_tools(
        self, state: ThreadState, tool_name: str, tool_args: dict
    ) -> None:
        """Audit bash commands for dangerous patterns before execution."""
        if tool_name != "bash":
            return

        command = tool_args.get("command", "")
        if not command:
            return

        risk, detail = self._classify(command)

        if risk == "HIGH":
            logger.warning(
                f"SandboxMiddleware: HIGH_RISK blocked command={command[:80]!r}"
            )
            state.next_action = "end"
        elif risk == "MEDIUM":
            logger.warning(
                f"SandboxMiddleware: MEDIUM_RISK warning command={command[:80]!r}"
            )

    async def after_tools_all(self, state: ThreadState) -> None:
        """Atomic release after all tools finish."""
        await self._release_if_needed(state)

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

    async def _release_if_needed(self, state: ThreadState) -> None:
        """Release sandbox if acquired."""
        if not state.sandbox or not state.sandbox.container_id:
            return

        thread_id = state.sandbox.thread_id
        try:
            await self.provider.release(state.sandbox)
            state.sandbox.status = "released"
        except Exception:
            pass
        finally:
            clear_sandbox_provider(thread_id)