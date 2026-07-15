"""Agent state — single source of truth."""

import time
from enum import Enum

from pydantic import BaseModel, Field

from .messages import BaseMessage


class NextAction(str, Enum):
    """Terminal result exposed by one agent run."""

    FINISH = "finish"
    WAIT = "wait"


class WaitState(BaseModel):
    """Durable description of the external input required to resume a thread."""

    question: str
    required_input: str | None = None
    tool_call_id: str
    reason: str | None = None
    created_at_ms: int = Field(default_factory=lambda: int(time.time() * 1000))


class SandboxState(BaseModel):
    exec_id: str | None = None
    container_id: str | None = None
    working_dir: str | None = None
    status: str | None = None


class AgentState(BaseModel):
    """Persistent conversation facts owned by exactly one active Agent."""
    thread_id: str | None = None
    messages: list[BaseMessage] = Field(default_factory=list)
    next_action: NextAction | None = None
    finish_reason: str = "running"
    wait: WaitState | None = None
    title: str | None = None
    revision: int = 0


# Backward-compatible name for public imports and persisted fixtures.
ThreadState = AgentState
