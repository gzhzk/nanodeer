"""Todo list tool."""

from langchain_core.tools import tool

from ..agent.memory.storage import MemoryStore
from ..plan.types import TodoItem


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
