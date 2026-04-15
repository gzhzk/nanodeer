"""Agent state — single source of truth flowing through the LangGraph."""

from enum import Enum
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field


class NextAction(str, Enum):
    """Control signals for LangGraph routing."""
    PROCESS = "process"
    WAIT = "wait"
    END = "end"


def merge_todos(existing: list[dict] | None, new: list[dict] | None) -> list[dict]:
    """Update or append todos: same id overwrites, otherwise appends."""
    if not existing:
        return new or []
    if not new:
        return existing

    result = {item["id"]: item for item in existing}
    for item in new:
        result[item["id"]] = item  # same id overwrites
    return list(result.values())


def merge_artifacts(existing: list[str] | None, new: list[str] | None) -> list[str]:
    """Reducer for artifacts — merges and deduplicates while preserving order."""
    if existing is None:
        return new or []
    if new is None:
        return existing
    return list(dict.fromkeys(existing + new))


class SandboxState(BaseModel):
    """Sandbox container reference — lifecycle managed outside the graph."""
    thread_id: str | None = None
    container_id: str | None = None
    working_dir: str | None = None
    status: str | None = None


class ThreadState(BaseModel):
    """Single source of truth flowing through the LangGraph.

    Fields:
        messages     — conversation history (LangGraph add_messages reducer)
        sandbox      — sandbox container reference
        title        — conversation title
        todos        — task list (id-based merge reducer)
        artifacts    — generated artifact paths (dedup merge reducer)
        next_action  — control signal (NextAction enum)
        thread_id    — thread identifier
        metadata     — middleware blackboard (paths, memory_context, uploaded_files, etc.)
    """
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    sandbox: SandboxState | None = None
    title: str | None = None
    todos: Annotated[list[dict], merge_todos] = Field(default_factory=list)
    artifacts: Annotated[list[str], merge_artifacts] = Field(default_factory=list)
    next_action: NextAction = NextAction.PROCESS
    thread_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
