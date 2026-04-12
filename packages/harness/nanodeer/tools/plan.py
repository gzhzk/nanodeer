"""Plan tools - direct MemoryStore integration for todo persistence."""

import uuid

from langchain_core.tools import tool

from ..agent.memory.storage import MemoryStore
from ..plan.types import TodoItem, TodoStatus


@tool
def write_todo(content: str, status: str = "pending", priority: int = 0) -> str:
    """Add a new todo item for task tracking.

    Use this to track complex multi-step tasks and their progress.
    Each todo has a status: pending, in_progress, or completed.

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
    store = MemoryStore()
    todos = store.load_todos("default")
    item = TodoItem(
        id=str(uuid.uuid4()),
        content=content,
        status=TodoStatus(status),
        priority=priority,
    )
    todos.append(item.to_dict())
    store.save_todos("default", todos)
    return f"Todo added: {item.to_markdown()}\nID: {item.id}"


@tool
def list_todos() -> str:
    """List all current todo items.

    Returns a formatted list of all todos with their status.

    Returns:
        Formatted list of todos with status indicators.
        "(no todos)" if empty.
    """
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

    Args:
        todo_id: The ID of the todo to mark as completed.

    Returns:
        Confirmation message, or error if not found.
    """
    store = MemoryStore()
    todos = store.load_todos("default")
    for t in todos:
        if t.get("id") == todo_id:
            t["status"] = "completed"
            store.save_todos("default", todos)
            return f"Todo `{todo_id}` marked as completed."
    return f"Todo `{todo_id}` not found."
