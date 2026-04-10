"""Agent state definitions."""

from enum import Enum
from typing import Annotated, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field

from ..container import SandboxInfo


class AgentMode(Enum):
    """Agent execution modes.

    Note: These are kept for state compatibility but mode routing
    is no longer used — the model decides tool usage autonomously.
    """
    DIRECT = "direct"
    REACT = "react"
    PLAN_EXECUTE = "plan"


def merge_todos(left, right):
    """Right wins - latest todo list is authoritative."""
    return right if right is not None else (left or [])


def merge_memory_context(left, right):
    """Right wins - latest memory context wins."""
    return right if right is not None else left


def merge_artifacts(left, right):
    """Merge with deduplication (first-occurrence order)."""
    if left is None:
        return right or []
    if right is None:
        return left
    return list(dict.fromkeys(left + right))


def merge_phase(left, right):
    """Forward only: planning → executing."""
    return right if right is not None else (left or "executing")


class ThreadState(BaseModel):
    """Agent state flowing through LangGraph.

    Fields:
        messages: Conversation history (input/output), [HumanMsg, AIMsg, ToolMsg...].
        artifacts: Tool execution artifact identifiers (plain strings, following DeerFlow).
        sandbox: Sandbox execution context (thread_id, container_id, status, working_dir).
        uploaded_files: User uploaded file paths.
        thread_id: Thread unique identifier.
        needs_clarification: Whether agent needs user clarification.
        pending_subagent_tasks: IDs of pending subagent tasks.
        memory_context: Injected memory context from long-term storage.
        todos: Plan mode task tracking list.
        mode: Execution mode (Direct/ReAct/PlanExecute).
        phase: Plan mode phase transition (planning → executing).
        subagent_results: Subagent execution results.
    """
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    artifacts: Annotated[list[str], merge_artifacts] = Field(default_factory=list)
    sandbox: SandboxInfo = Field(default_factory=lambda: SandboxInfo(thread_id=""))
    uploaded_files: list[dict] = Field(default_factory=list)
    thread_id: str | None = Field(default=None)
    needs_clarification: bool = Field(default=False)
    pending_subagent_tasks: list[str] = Field(default_factory=list)
    memory_context: Annotated[str | None, merge_memory_context] = Field(default=None)
    todos: Annotated[list[dict], merge_todos] = Field(default_factory=list)
    mode: AgentMode = Field(default=AgentMode.REACT)
    phase: Annotated[Literal["planning", "executing"], merge_phase] = Field(default="executing")
    subagent_results: list[dict] = Field(default_factory=list)
