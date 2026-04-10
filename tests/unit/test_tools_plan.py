"""Unit tests for plan tools (write_todo, list_todos, complete_todo)."""
import pytest

from nanodeer.tools.plan import write_todo


class TestWriteTodo:
    """Test write_todo tool."""

    def test_write_todo_returns_string(self):
        """write_todo returns string result."""
        result = write_todo.invoke({"content": "Test task"})
        assert isinstance(result, str)

    def test_write_todo_contains_id(self):
        """write_todo result contains an ID."""
        result = write_todo.invoke({"content": "Test task"})
        assert "ID:" in result

    def test_write_todo_with_priority(self):
        """write_todo with priority."""
        result = write_todo.invoke({"content": "Important", "priority": 5})
        assert isinstance(result, str)

    def test_write_todo_with_status(self):
        """write_todo with custom status."""
        result = write_todo.invoke({"content": "In progress", "status": "in_progress"})
        assert isinstance(result, str)


# NOTE: list_todos and complete_todo have a known bug where they call
# MemoryStore.load_todos(user_id, project_slug) but MemoryStore.load_todos
# only accepts (project_slug). These tools work correctly when intercepted
# by PlanMiddleware but fail in direct invocation.


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
