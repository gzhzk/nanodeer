"""Agent state definitions."""

from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field

from .router import AgentMode
from ..sandbox import SandboxInfo  # SandboxInfo lives in sandbox/ layer


# class Artifact(BaseModel):
#     """Artifact structure.
#
#     Currently unused (artifacts are list[str]).
#     Reserved for future extensibility when:
#     - Sandbox layer needs version tracking
#     - Memory layer extracts structured facts
#     - Subagent coordination with structured output
#
#     If re-enabled, merge_artifacts should use Artifact objects
#     with id-based deduplication.
# """
#     id: str
#     type: str  # "file", "image", "code"
#     content: str
#     path: str | None = None


def merge_todos(left: list[dict] | None, right: list[dict] | None) -> list[dict]:
    """Replace semantics: tool writes are authoritative, right wins.

    Each write_todo/complete_todo call produces a complete new todo list.
    The latest update is always authoritative.
    """
    return right if right is not None else (left or [])


def merge_memory_context(left: str | None, right: str | None) -> str | None:
    """Replace semantics: latest memory context wins.

    memory_context is loaded fresh from file on before_agent_start.
    Middleware updates it after save_memory calls; LangGraph reducer
    merges the update into state.
    """
    return right if right is not None else left


def merge_artifacts(
    left: list[str] | None, right: list[str] | None
) -> list[str]:
    """Merge two artifact lists with deduplication by string identity.

    Follows DeerFlow's minimal design: artifacts are plain strings.
    Each tool returns a unique string identifier; deduplication prevents
    duplicate artifacts from multiple tool calls.

    Args:
        left: Existing artifact strings.
        right: New artifact strings to merge.

    Returns:
        Merged list with duplicates removed, preserving first-occurrence order.
    """
    if left is None:
        return right or []
    if right is None:
        return left
    return list(dict.fromkeys(left + right))


from typing import Literal


def merge_phase(left: Literal["planning", "executing"] | None, right: Literal["planning", "executing"] | None) -> Literal["planning", "executing"]:
    """Phase transitions forward only: planning → executing. Never goes back."""
    return right if right is not None else (left or "executing")


class ThreadState(BaseModel):
    """Main agent state that flows through the LangGraph.

    Fields:
        messages: Conversation history (input/output).
        artifacts: Tool execution artifact identifiers (plain strings, following DeerFlow).
        sandbox: Sandbox execution context (thread_id, container_id, status, working_dir).
        uploaded_files: User uploaded file paths.
        thread_id: Thread unique identifier.
        needs_clarification: Whether agent needs user clarification.
        pending_subagent_tasks: IDs of pending subagent tasks.
    """
    messages: Annotated[list[BaseMessage], add_messages] = Field(
        default_factory=list,
    )
    artifacts: Annotated[list[str], merge_artifacts] = Field(
        default_factory=list,
    )
    sandbox: SandboxInfo = Field(default_factory=lambda: SandboxInfo(thread_id=""))
    uploaded_files: list[dict] = Field(default_factory=list)  # [{name, content, mime_type}, ...]
    thread_id: str | None = Field(default=None)
    needs_clarification: bool = Field(default=False)
    pending_subagent_tasks: list[str] = Field(default_factory=list)
    memory_context: Annotated[str | None, merge_memory_context] = Field(default=None)
    todos: Annotated[list[dict], merge_todos] = Field(default_factory=list)  # Plan mode task tracking
    mode: AgentMode = Field(default=AgentMode.REACT)  # Execution mode (Direct/ReAct/PlanExecute)
    phase: Annotated[Literal["planning", "executing"], merge_phase] = Field(default="executing")  # Plan mode: planning → executing
    subagent_results: list[dict] = Field(default_factory=list)  # Subagent execution results
