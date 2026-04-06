"""Agent state definitions."""

from typing import Annotated, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field


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
#     """
#     id: str
#     type: str  # "file", "image", "code"
#     content: str
#     path: str | None = None


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


class SandboxInfo(BaseModel):
    """Sandbox execution context for a thread.

    Represents a sandboxed execution environment (always Docker container).
    Must be acquired before any tool execution; never nullable.
    """
    thread_id: str
    container_id: str | None = None  # Filled after container is created
    status: Literal["acquiring", "ready", "released"] = "acquiring"
    working_dir: str | None = None  # Physical path inside container


class ThreadState(BaseModel):
    """Main agent state that flows through the LangGraph.

    Fields:
        messages: Conversation history (input/output).
        artifacts: Tool execution artifact identifiers (plain strings, following DeerFlow).
        sandbox: Sandbox execution context (thread_id, sandbox_type, working_dir).
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
    memory_context: str | None = Field(default=None)
    todos: list[dict] = Field(default_factory=list)  # Plan mode task tracking
