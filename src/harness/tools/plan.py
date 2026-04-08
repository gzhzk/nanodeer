"""Plan mode tools for NanoDeer."""

from langchain_core.tools import tool

from ..plan.types import TodoItem, TodoStatus


@tool
def write_todo(content: str, status: str = "pending", priority: int = 0) -> str:
    """Add or update a todo item for task tracking.

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
        Confirmation message with todo details.
    """
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
    Note: In REACT/PLAN mode, todos are tracked in ThreadState.todos.
    This tool returns the current list; the agent should pass the result
    back to the user.

    Returns:
        Formatted list of todos. "(no todos)" if empty.
    """
    # TODO: Connect to TodoListMiddleware for state-aware implementation
    # Currently returns a marker that the middleware will replace
    return "[TODOS_PLACEHOLDER]"


@tool
def complete_todo(todo_id: str) -> str:
    """Mark a todo item as completed.

    Args:
        todo_id: The ID of the todo to mark as completed.

    Returns:
        Confirmation message.
    """
    # TODO: Connect to TodoListMiddleware for state-aware implementation
    return f"[COMPLETE_PLACEHOLDER:{todo_id}]"