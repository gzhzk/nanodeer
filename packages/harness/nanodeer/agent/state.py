"""Agent state — single source of truth."""

from dataclasses import dataclass
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
    error: dict | None = None       # {"type": "...", "detail": "..."} set by Detection, handled by Handling


def _merge_by_id(existing, new, id_key="id"):
    if not existing:
        return new or []
    if not new:
        return existing
    result = {item[id_key]: item for item in existing}
    for item in new:
        result[item[id_key]] = item
    return list(result.values())


def merge_todos(existing, new):
    return _merge_by_id(existing, new, "id")


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
    todos: Annotated[list[dict], merge_todos] = Field(default_factory=list)
    artifacts: Annotated[list[str], merge_artifacts] = Field(default_factory=list)
    title: str | None = None
    sandbox: SandboxState | None = None
