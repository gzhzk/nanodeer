"""PlanMiddleware - manages planning state and task tracking.

Broader than todo list: manages planning workflow including
task tracking, plan persistence, and planning phase coordination.

Intercepts write_todo/complete_todo/list_todos tool calls to keep
state.todos in sync. Persistence via LangGraph checkpointer + file backup.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .base import Middleware
from ...plan.types import TodoItem, TodoStatus

if TYPE_CHECKING:
    from ..memory.storage import MemoryStore


class PlanMiddleware(Middleware):
    """Manages planning state and task tracking.

    - Loads todos from memory store before agent starts
    - Intercepts todo tools to keep state.todos in sync
    - Backup to file on after_agent_end

    This middleware enables plan_mode: the agent uses WriteTodo to
    create a plan, then executes tasks in order.

    Storage: ~/.nanodeer/memory/{user_id}/todos/{project_slug}.json
    """

    def __init__(
        self,
        memory_store: "MemoryStore | None" = None,
        project_slug: str = "default",
    ):
        """Initialize PlanMiddleware.

        Args:
            memory_store: MemoryStore instance. Defaults to new MemoryStore().
            project_slug: Project identifier for project-specific plans.
        """
        if memory_store is None:
            from ..memory.storage import MemoryStore
            memory_store = MemoryStore()
        self.memory_store = memory_store
        self.project_slug = project_slug
        self._user_id = "nanodeer-shared"

    async def before_agent_start(self, state: Any) -> None:
        """Load todos into state."""
        todos = self.memory_store.load_todos(self._user_id, self.project_slug)
        if isinstance(state, dict):
            state["todos"] = todos
        else:
            state.todos = todos

    async def after_tool_call(
        self,
        state: Any,
        tool_name: str,
        tool_args: dict,
        result: str,
    ) -> str:
        """Intercept todo tools to update state.todos."""
        if tool_name == "write_todo":
            return self._handle_write_todo(state, tool_args, result)
        elif tool_name == "complete_todo":
            return self._handle_complete_todo(state, tool_args, result)
        elif tool_name == "list_todos":
            return self._handle_list_todos(state, result)
        return result

    def _handle_write_todo(
        self, state: Any, tool_args: dict, result: str
    ) -> str:
        """Handle write_todo: extract ID from result, build todo, update state."""
        todo_id = None
        for line in result.split("\n"):
            if line.startswith("ID:"):
                todo_id = line.split("ID:", 1)[1].strip()
                break

        if not todo_id:
            todo_id = str(uuid.uuid4())

        content = tool_args.get("content", "")
        status_str = tool_args.get("status", "pending")
        priority = tool_args.get("priority", 0)

        new_todo = {
            "id": todo_id,
            "content": content,
            "status": TodoStatus(status_str).value,
            "priority": priority,
            "created_at": datetime.now().isoformat(),
        }

        if isinstance(state, dict):
            current_todos = state.get("todos", [])
        else:
            current_todos = list(getattr(state, "todos", []))

        new_todos = current_todos + [new_todo]

        if isinstance(state, dict):
            state["todos"] = new_todos
        else:
            state.todos = new_todos

        return result

    def _handle_complete_todo(
        self, state: Any, tool_args: dict, result: str
    ) -> str:
        """Handle complete_todo: mark todo as completed, update state."""
        todo_id = tool_args.get("todo_id", "")

        if isinstance(state, dict):
            current_todos = state.get("todos", [])
        else:
            current_todos = list(getattr(state, "todos", []))

        updated = False
        new_todos = []
        for t in current_todos:
            if t.get("id") == todo_id:
                new_todos.append({**t, "status": TodoStatus.COMPLETED.value})
                updated = True
            else:
                new_todos.append(t)

        if updated:
            if isinstance(state, dict):
                state["todos"] = new_todos
            else:
                state.todos = new_todos
            return result
        else:
            return f"Todo `{todo_id}` not found."

    def _handle_list_todos(self, state: Any, result: str) -> str:
        """Handle list_todos: return todos from state, not from file."""
        if isinstance(state, dict):
            current_todos = state.get("todos", [])
        else:
            current_todos = list(getattr(state, "todos", []))

        if not current_todos:
            return "(no todos)"

        lines = []
        for t in current_todos:
            item = TodoItem.from_dict(t)
            status_icon = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]",
            }.get(item.status.value, "[ ]")
            lines.append(f"{status_icon} {item.content}  `(id={item.id})`")

        return "\n".join(lines)

    async def after_agent_end(self, state: Any) -> None:
        """Backup save todos to file after agent ends."""
        if isinstance(state, dict):
            todos = state.get("todos", [])
        else:
            todos = list(getattr(state, "todos", []))

        if not todos:
            return

        self.memory_store.save_todos(self._user_id, self.project_slug, todos)
