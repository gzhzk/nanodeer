"""Agent state — single source of truth."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field

from .messages import BaseMessage


class NextAction(str, Enum):
    PROCESS = "process"
    WAIT = "wait"
    END = "end"


@dataclass
class TurnSignals:
    """Per-turn data carrier — produced and consumed within a single ReAct turn.

    Middlewares write signals; the Executor reads them to control routing or
    bundle data for prompt/caller. Each turn starts fresh with a new instance.
    """
    clarification_question: str | None = None
    memory_context: str | None = None
    plan_context: str | None = None
    error: dict | None = None       # {"type": "...", "detail": "..."} set by Detection, handled by Handling
    skip_tool: bool = False          # If True, tools loop skips sandbox exec and uses skip_tool_result
    skip_tool_result: str | None = None  # Pre-computed result when skip_tool is True
    events: list = field(default_factory=list)  # JSON-serializable events for --json-events output
    uploaded_files_list: str | None = None  # Formatted file list from FileMiddleware, for prompt injection
    _uploaded_files: list[dict] | None = None  # Internal: raw uploads from app layer to FileMiddleware


def merge_artifacts(existing, new):
    if not existing:
        return new or []
    if not new:
        return existing
    return list(dict.fromkeys(existing + new))


class SandboxState(BaseModel):
    exec_id: str | None = None
    container_id: str | None = None
    working_dir: str | None = None
    status: str | None = None


class ThreadState(BaseModel):
    """Persistent conversation-scoped state — survives across turns and supports snapshot."""
    thread_id: str | None = None
    messages: list[BaseMessage] = Field(default_factory=list)
    next_action: NextAction = NextAction.PROCESS
    artifacts: Annotated[list[str], merge_artifacts] = Field(default_factory=list)
    title: str | None = None
    sandbox: SandboxState | None = None
    system_prompt: str | None = None  # cached static system prompt (built once, reused every turn)
