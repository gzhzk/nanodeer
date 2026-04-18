"""Todo write tool - create or update tasks."""

import uuid

from langchain_core.tools import tool

from ..plan.loader import TodoStore
from ..plan.types import TodoItem, TodoStatus


@tool
def write_todo(
    content: str | None = None,
    id: str | None = None,
    status: str | None = None,
    priority: int | None = None,
) -> str:
    """Create a new todo or update an existing one by ID.

    Use this to track complex multi-step tasks and their progress.
    Each todo has a status: pending, in_progress, or completed.

    To create: omit id. A new todo is appended with the given content.
    To update: provide id. content/status/priority fields are merged onto the existing item.

    Args:
        content: The task description (required for new todos, optional for updates).
        id: Todo ID to update. If omitted, creates a new todo.
        status: Task status. Options: "pending", "in_progress", "completed".
        priority: Priority level (higher = more important).

    Returns:
        Confirmation message with todo details and ID.
    """
    store = TodoStore()
    todos = store.load("default")

    if id is not None:
        # Update existing todo
        found = False
        for t in todos:
            if t.get("id") == id:
                if content is not None:
                    t["content"] = content
                if status is not None:
                    t["status"] = status
                if priority is not None:
                    t["priority"] = priority
                store.save("default", todos)
                found = True
                item = TodoItem.from_dict(t)
                return f"Todo updated: {item.to_markdown()}\nID: {item.id}"
        if not found:
            return f"Todo `{id}` not found."

    # Create new todo
    if content is None:
        return "content is required when creating a new todo."
    item = TodoItem(
        id=str(uuid.uuid4()),
        content=content,
        status=TodoStatus(status or "pending"),
        priority=priority or 0,
    )
    todos.append(item.to_dict())
    store.save("default", todos)
    return f"Todo added: {item.to_markdown()}\nID: {item.id}"
