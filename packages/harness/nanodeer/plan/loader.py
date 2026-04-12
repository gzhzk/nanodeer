"""Plan module - task tracking and planning."""

from .types import TodoItem, TodoStatus, TODOS_SECTION_TEMPLATE

__all__ = [
    "TodoItem",
    "TodoStatus",
    "TODOS_SECTION_TEMPLATE",
    "PlanLoader",
]


class PlanLoader:
    """Loads and manages plan (todo list) context for agent execution.

    Integrates with MemoryStore for persistence.
    """

    def __init__(self, memory_store=None):
        self._memory_store = memory_store

    def load(self, project_slug: str = "default") -> str:
        """Load plan context as formatted string for metadata injection.

        Args:
            project_slug: Project identifier.

        Returns:
            Formatted todos section for prompt injection.
        """
        if self._memory_store:
            todos = self._memory_store.load_todos(project_slug)
            if todos:
                lines = []
                for t in todos:
                    item = TodoItem.from_dict(t)
                    lines.append(item.to_markdown())
                return TODOS_SECTION_TEMPLATE.format(todos="\n".join(lines))
        return ""

    def update(self, state) -> None:
        """Update plan state after LLM output.

        Currently a no-op - todo updates are handled via tool calls.
        This method exists for future hook extensibility.

        Args:
            state: ThreadState from the agent.
        """
        pass
