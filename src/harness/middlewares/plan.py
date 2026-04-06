"""TodoList middleware for task tracking.

Loads todos from memory store before agent starts and injects into state.
"""

from typing import TYPE_CHECKING, Any

from ..middlewares.base import Middleware

if TYPE_CHECKING:
    from ..memory.storage import MemoryStore


class TodoListMiddleware(Middleware):
    """Manages todo list state for task tracking.

    Loads todos from memory store before agent starts and injects into
    state.todos. Saves todos after agent ends.

    Storage: ~/.nanodeer/memory/{user_id}/todos/{project_slug}.json
    """

    def __init__(
        self,
        memory_store: "MemoryStore",
        project_slug: str = "default",
    ):
        """Initialize TodoListMiddleware.

        Args:
            memory_store: MemoryStore instance for persistence.
            project_slug: Project identifier for project-specific todos.
        """
        self.memory_store = memory_store
        self.project_slug = project_slug

    async def before_agent_start(self, state: Any) -> None:
        """Load todos into state.

        Args:
            state: Current ThreadState (or dict).
        """
        if isinstance(state, dict):
            thread_id = state.get("thread_id") or "default"
            todos = self.memory_store.load_todos(thread_id, self.project_slug)
            state["todos"] = todos
        else:
            thread_id = getattr(state, "thread_id", None) or "default"
            todos = self.memory_store.load_todos(thread_id, self.project_slug)
            state.todos = todos

    async def after_agent_end(self, result: dict) -> None:
        """Save todos to memory store.

        Args:
            result: Final state dict from agent execution.
        """
        todos = result.get("todos", [])
        if not todos:
            return

        # Get user_id from result if available
        user_id = result.get("thread_id", "default")
        self.memory_store.save_todos(user_id, self.project_slug, todos)
