"""Agent state — single source of truth."""

from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field

from .messages import BaseMessage


class NextAction(str, Enum):
    PROCESS = "process"
    WAIT = "wait"
    END = "end"


@dataclass
class TurnSignals:
    """Per-turn data carrier — produced and consumed within a single ReAct turn."""
    clarification_question: str | None = None
    memory_context: str | None = None
    plan_context: str | None = None
    events: list = field(default_factory=list)
    uploaded_files_list: str | None = None
    uploaded_files: list[dict] | None = None


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
    finish_reason: str = "running"  # why the last turn ended: completed/repeated_tool_calls/max_turns/bash_blocked/sandbox_released
    title: str | None = None
    sandbox: SandboxState | None = None
    system_prompt: str | None = None  # cached static system prompt (built once, reused every turn)
