"""SandboxMiddleware - manages container lifecycle and audits bash commands."""
import logging
import re

from nanodeer.agent.state import ThreadState
from nanodeer.config import get_config
from nanodeer.sandbox import Sandbox, set_sandbox, clear_sandbox, SandboxProvider
from nanodeer.sandbox.docker import DockerSandboxProvider

from .base import Middleware

logger = logging.getLogger(__name__)

_HIGH_RISK = [
    re.compile(r"^\s*>\s*/etc/passwd", re.I),
    re.compile(r"^\s*>\s*/etc/shadow", re.I),
    re.compile(r"^\s*>\s*/etc/sudoers"),
    re.compile(r"rm\s+-rf\s+/\s*(--.*)?$", re.I),
    re.compile(r"rm\s+-rf\s+/\*\s*$", re.I),
    re.compile(r":\(\)\s*\{\s*\|\s*:\s*&\s*\}\s*;", re.I),
    re.compile(r"(curl|wget).*\|\s*(bash|sh)", re.I),
    re.compile(r"dd\s+if=", re.I),
    re.compile(r"mkfs", re.I),
    re.compile(r"chmod\s+4777", re.I),
]

_MEDIUM_RISK = [
    re.compile(r"chmod\s+777\b", re.I),
    re.compile(r"chmod\s+000\b", re.I),
    re.compile(r"\bpip\s+install\b", re.I),
    re.compile(r"\bapt-get\s+install\b", re.I),
    re.compile(r"\bnpm\s+install\b", re.I),
    re.compile(r"\bnmap\b", re.I),
    re.compile(r":\(|:{:|:&"),
]


class SandboxMiddleware(Middleware):
    """Manages sandbox lifecycle and audits bash commands."""

    def __init__(self, provider: SandboxProvider | None = None):
        cfg = get_config()
        self._provider = provider or DockerSandboxProvider(
            image=cfg.sandbox.image,
            container_prefix=cfg.sandbox.container_prefix,
            network_mode=cfg.sandbox.network_mode,
        )

    async def before_llm(self, state: ThreadState) -> None:
        if state.sandbox and state.sandbox.container_id:
            return
        if not state.thread_id:
            raise ValueError("SandboxMiddleware requires thread_id in state")

        sandbox = await self._provider.acquire(state.thread_id)
        state.sandbox.thread_id = sandbox.thread_id
        state.sandbox.container_id = sandbox.container_id
        state.sandbox.working_dir = sandbox.working_dir
        state.sandbox.status = "ready"
        set_sandbox(state.thread_id, sandbox)

    async def before_tools(self, state: ThreadState, tool_name: str, tool_args: dict) -> None:
        if tool_name != "bash":
            return
        cmd = tool_args.get("command", "")
        if not cmd:
            return

        risk, _ = self._classify(cmd)
        if risk == "HIGH":
            logger.warning(f"HIGH_RISK blocked: {cmd[:80]!r}")
            state.next_action = "end"
        elif risk == "MEDIUM":
            logger.warning(f"MEDIUM_RISK warning: {cmd[:80]!r}")

    async def after_tools_all(self, state: ThreadState) -> None:
        await self._release_if_needed(state)

    def _classify(self, command: str) -> tuple[str, str]:
        """Classify command risk by pattern-matching the full command string.

        Note: shlex.split is not used for classification — it only validates
        command structure. The actual classification scans the full command
        string for dangerous patterns regardless of shell quoting.
        """
        for p in _HIGH_RISK:
            if p.search(command):
                return "HIGH", p.pattern
        for p in _MEDIUM_RISK:
            if p.search(command):
                return "MEDIUM", p.pattern
        return "LOW", ""

    async def _release_if_needed(self, state: ThreadState) -> None:
        if not state.sandbox or not state.sandbox.container_id:
            return
        tid = state.sandbox.thread_id
        try:
            await self._provider.release(state.sandbox)
            state.sandbox.status = "released"
        except Exception:
            pass
        finally:
            clear_sandbox(tid)
