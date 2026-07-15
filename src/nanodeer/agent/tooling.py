"""One narrow boundary for tool policy, backend preparation, and invocation."""

from __future__ import annotations

import contextvars
import inspect
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

logger = logging.getLogger(__name__)

_active_tool_call_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "nanodeer_tool_call_id",
    default=None,
)

_HIGH_RISK = (
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
)

_MEDIUM_RISK = (
    re.compile(r"chmod\s+777\b", re.I),
    re.compile(r"chmod\s+000\b", re.I),
    re.compile(r"\bpip\s+install\b", re.I),
    re.compile(r"\bapt-get\s+install\b", re.I),
    re.compile(r"\bnpm\s+install\b", re.I),
    re.compile(r"\bnmap\b", re.I),
    re.compile(r":\(|:{:|:&"),
)

_SHELL_METACHAR = frozenset((";", "&&", "||", "|", ">", ">>", "<", "`", "$("))


@dataclass(frozen=True)
class ToolExecution:
    content: Any
    success: bool
    blocked: bool = False
    block_reason: str | None = None


def current_tool_call_id() -> str | None:
    """Stable idempotency key visible to tools during the current invocation."""
    return _active_tool_call_id.get()


def bash_safe(tool_name: str, args: dict) -> bool:
    """Block destructive bash patterns while allowing normal shell composition."""
    if tool_name != "bash":
        return True
    command = args.get("command", "")
    if not command:
        return True
    if any(marker in command for marker in _SHELL_METACHAR):
        logger.warning("Shell metachar in command (warn-only): %r", command[:80])
    if any(pattern.search(command) for pattern in _HIGH_RISK):
        logger.warning("High risk blocked: %r", command[:80])
        return False
    if any(pattern.search(command) for pattern in _MEDIUM_RISK):
        logger.warning("Medium risk command: %r", command[:80])
    return True


def tool_success(content: Any, explicit_success: bool = True) -> bool:
    if not explicit_success:
        return False
    text = str(content)
    if "<subagent_result>" in text and any(
        marker in text
        for marker in ("(failed)", "(timeout)", "(cancelled)", "\nError:")
    ):
        return False
    return not (
        text.startswith("Error:")
        or text.startswith("Error executing ")
        or " not found" in text[:120]
        or "requires parameters:" in text[:160]
    )


async def _invoke(tool, args: dict, exec_id: str | None) -> Any:
    if hasattr(tool, "get_sandbox_command"):
        result = tool.ainvoke(args, exec_id=exec_id)
    elif getattr(tool, "coroutine", None) is not None:
        result = tool.ainvoke(args)
    elif hasattr(tool, "invoke"):
        result = tool.invoke(args)
    else:
        result = tool.ainvoke(args, exec_id=exec_id)
    return await result if inspect.isawaitable(result) else result


async def execute_tool(
    tool,
    call: dict,
    *,
    exec_id: str | None,
    prepare_backend: Callable[[], Awaitable[None]] | None = None,
) -> ToolExecution:
    """Execute one committed ToolCall without mutating AgentState or emitting Events."""
    name = str(call.get("name") or "")
    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    call_id = str(call.get("id") or "")

    if name == "wait":
        content = "Error: wait must be the only tool call in its turn and requires a non-empty question."
        return ToolExecution(content=content, success=False)
    if not bash_safe(name, args):
        return ToolExecution(
            content="Blocked by bash audit",
            success=False,
            blocked=True,
            block_reason="bash_audit",
        )
    if tool is None:
        return ToolExecution(content=f"Tool {name} not found", success=False)
    token = _active_tool_call_id.set(call_id or None)
    try:
        if getattr(tool, "requires_sandbox", False):
            if prepare_backend is None:
                return ToolExecution(
                    content="Error: isolated execution backend is unavailable",
                    success=False,
                )
            await prepare_backend()
        content = await _invoke(tool, args, exec_id)
        return ToolExecution(content=content, success=tool_success(content))
    except ValidationError as exc:
        fields = [str(error.get("loc", ["?"])[0]) for error in exc.errors()]
        logger.warning("tool=%s call_id=%s validation_error fields=%s", name, call_id, fields)
        return ToolExecution(
            content=f"Tool '{name}' requires parameters: {', '.join(fields)}.",
            success=False,
        )
    except Exception as exc:
        logger.warning("tool=%s call_id=%s error=%s", name, call_id, exc)
        return ToolExecution(content=f"Error executing {name}: {exc}", success=False)
    finally:
        _active_tool_call_id.reset(token)


__all__ = [
    "ToolExecution",
    "bash_safe",
    "current_tool_call_id",
    "execute_tool",
    "tool_success",
]
