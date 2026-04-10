"""Plan mode tools for NanoDeer.

These tools are PURE execution units — they only return structured data.
Storage/persistence is handled by TodoListMiddleware via after_tool_call.

The write_todo tool returns a unique ID that the middleware uses to
reconstruct the full todo dict and update state.todos.
"""

import uuid
from datetime import datetime

from langchain_core.tools import tool

from ..agent.memory.storage import MemoryStore
from ..plan.types import TodoItem, TodoStatus

# Shared user_id for todo storage (matches TodoListMiddleware)
_TODO_USER_ID = "nanodeer-shared"


@tool
def write_todo(content: str, status: str = "pending", priority: int = 0) -> str:
    """Add a new todo item for task tracking.

    Use this to track complex multi-step tasks and their progress.
    Each todo has a status: pending, in_progress, or completed.

    The todo is NOT persisted immediately — TodoListMiddleware.after_tool_call
    intercepts this call and updates state.todos for LangGraph state persistence.

    Args:
        content: The task description (what needs to be done).
        status: Task status. Options:
               - "pending": Not started yet (default)
               - "in_progress": Currently being worked on
               - "completed": Done
        priority: Priority level (higher = more important). Default 0.

    Returns:
        Confirmation message with todo details and ID for tracking.
    """
    # Pure execution: just validate and return structured data
    item = TodoItem(
        content=content,
        status=TodoStatus(status),
        priority=priority,
    )
    return f"Todo added: {item.to_markdown()}\nID: {item.id}"


@tool
def list_todos() -> str:
    """List all current todo items.

    Returns a formatted list of all todos with their status.

    NOTE: This tool reads from LangGraph state, not from file directly.
    The actual todos are maintained in state.todos by TodoListMiddleware.

    Returns:
        Formatted list of todos with status indicators.
        "(no todos)" if empty.
    """
    # Note: This function is normally intercepted by TodoListMiddleware.after_tool_call
    # which returns the actual state.todos. This is a fallback for direct invocation.
    store = MemoryStore()
    todos = store.load_todos("default")

    if not todos:
        return "(no todos)"

    lines = []
    for t in todos:
        item = TodoItem.from_dict(t)
        status_icon = {
            "pending": "[ ]",
            "in_progress": "[>]",
            "completed": "[x]",
        }.get(item.status.value, "[ ]")
        lines.append(f"{status_icon} {item.content}  `(id={item.id})`")

    return "\n".join(lines)


@tool
def complete_todo(todo_id: str) -> str:
    """Mark a todo item as completed by its ID.

    NOTE: This tool is intercepted by TodoListMiddleware.after_tool_call
    which updates state.todos for LangGraph state persistence.
    In direct invocation (testing), falls back to MemoryStore lookup.

    Args:
        todo_id: The ID of the todo to mark as completed.

    Returns:
        Confirmation message, or error if not found.
    """
    # Fallback validation for direct invocation (testing/non-agent context)
    store = MemoryStore()
    todos = store.load_todos("default")
    for t in todos:
        if t.get("id") == todo_id:
            return f"Todo `{todo_id}` marked as completed."
    return f"Todo `{todo_id}` not found."
