"""Agent state — single source of truth flowing through the LangGraph."""

from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field


def merge_todos(existing: list | None, new: list | None) -> list | None:
    """Reducer for todos — appends new items, avoids None overwrite."""
    if existing is None:
        return new or None
    if new is None:
        return existing
    return existing + new


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


class ThreadDataState(BaseModel):
    """Per-thread directory structure on host machine."""
    workspace_path: str | None = None
    uploads_path: str | None = None
    outputs_path: str | None = None


class ThreadState(BaseModel):
    """Single source of truth flowing through the LangGraph.

    Fields:
        messages     — conversation history (LangGraph add_messages reducer)
        sandbox      — sandbox container reference (not the container itself)
        thread_data  — per-thread directory paths
        title        — conversation title
        todos        — task list (append reducer)
        artifacts    — generated artifact paths (dedup merge reducer)
        next_action  — control signal ("process" | "wait_for_clarification" | "end")
        thread_id    — thread identifier
        metadata     — middleware blackboard (memory_context, uploaded_files, etc.)
    """
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    sandbox: SandboxState | None = None
    thread_data: ThreadDataState | None = None
    title: str | None = None
    todos: Annotated[list | None, merge_todos] = Field(default=None)
    artifacts: Annotated[list[str], merge_artifacts] = Field(default_factory=list)
    next_action: str = "process"
    thread_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
