"""SandboxMiddleware - manages container lifecycle and audits bash commands."""
import logging
import re

from nanodeer.agent.state import NextAction, SandboxState, ThreadState, TurnSignals
from nanodeer.config import get_config
from nanodeer.sandbox import Sandbox, get_sandbox, set_sandbox, clear_sandbox, SandboxProvider
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
            base_path=cfg.sandbox.base_path,
        )

    async def before_llm_streaming(self, state: ThreadState, signals: TurnSignals):
        if state.sandbox is None:
            state.sandbox = SandboxState()
        if state.sandbox.container_id:
            return  # already acquired this turn
        yield  # make it an async generator

        # Check module-level context (persists across turns for WAIT scenarios)
        if state.thread_id:
            existing = get_sandbox(state.thread_id)
            if existing:
                state.sandbox.exec_id = existing.exec_id
                state.sandbox.container_id = existing.container_id
                state.sandbox.working_dir = existing.working_dir
                state.sandbox.status = "ready"
                return

        if not state.thread_id:
            raise ValueError("SandboxMiddleware requires thread_id in state")

        sandbox = await self._provider.acquire(state.thread_id)
        state.sandbox.exec_id = sandbox.exec_id
        state.sandbox.container_id = sandbox.container_id
        state.sandbox.working_dir = sandbox.working_dir
        state.sandbox.status = "ready"
        set_sandbox(state.thread_id, sandbox)
        signals.events.append({
            "type": "sandbox_acquired",
            "exec_id": sandbox.exec_id,
        })

    async def after_llm_streaming(self, state: ThreadState, signals: TurnSignals):
        """Release container on END after LLM — covers LLM-ended sessions (no tools loop)."""
        if state.next_action == NextAction.END:
            await self._release_if_needed(state)
        return
        yield

    # Shell metacharacters that allow command chaining — hard block regardless of other intent.
    _SHELL_METACHAR = frozenset([";", "&&", "||", "|", ">", ">>", "<", "`", "$("])

    async def before_tools_streaming(
        self, state: ThreadState, signals: TurnSignals, tool_name: str, tool_args: dict
    ):
        # Memory tools are handled directly on the host by MemoryMiddleware — skip sandbox routing.
        if getattr(signals, "skip_tool", False):
            return
        yield  # make it an async generator

        if tool_name != "bash":
            return

        signals.events.append({
            "type": "tool_call",
            "name": "bash",
            "command": tool_args.get("command", "")[:100],
        })
        cmd = tool_args.get("command", "")
        if not cmd:
            return

        # Hard block: command chaining metacharacters are never allowed in user bash commands.
        if any(meta in cmd for meta in self._SHELL_METACHAR):
            logger.warning(f"Shell metacharacters blocked: {cmd[:80]!r}")
            state.next_action = NextAction.END
            return

        risk, _ = self._classify(cmd)
        if risk == "HIGH":
            logger.warning(f"HIGH_RISK blocked: {cmd[:80]!r}")
            state.next_action = NextAction.END
        elif risk == "MEDIUM":
            logger.warning(f"MEDIUM_RISK warning: {cmd[:80]!r}")

    async def after_tools_all_streaming(self, state: ThreadState, signals: TurnSignals):
        # Release only when session is done (END), not between turns.
        # Sandbox must persist across PROCESS turns — react.py reuses it.
        if state.next_action == NextAction.END:
            await self._release_if_needed(state)
        return
        yield

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
        # Idempotent: skip if already released (prevents double-release)
        if state.sandbox.status == "released":
            return
        exec_id = state.sandbox.exec_id
        try:
            await self._provider.release(state.sandbox)
        except Exception:
            pass
        finally:
            if exec_id:
                clear_sandbox(exec_id)
            state.sandbox.status = "released"  # always update, even on error
