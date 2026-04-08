"""Test 08: Plan mode - todo tracking and planning."""

import tempfile
from pathlib import Path

import pytest

from harness.plan import TodoItem, TodoStatus
from harness.tools import write_todo, list_todos, complete_todo
from harness.middlewares import TodoListMiddleware
from harness.memory import MemoryStore


class TestTodoItem:
    """Test TodoItem data structure."""

    def test_todo_creation(self):
        """TodoItem creates with defaults."""
        item = TodoItem(content="Test task")
        assert item.content == "Test task"
        assert item.status == TodoStatus.PENDING
        assert item.priority == 0
        assert item.id.startswith("todo-")

    def test_todo_to_markdown_pending(self):
        """Pending todo shows unchecked box."""
        item = TodoItem(content="Test task", status=TodoStatus.PENDING)
        assert item.to_markdown() == "[ ] Test task"

    def test_todo_to_markdown_in_progress(self):
        """In progress todo shows arrow."""
        item = TodoItem(content="Test task", status=TodoStatus.IN_PROGRESS)
        assert item.to_markdown() == "[>] Test task"

    def test_todo_to_markdown_completed(self):
        """Completed todo shows checked box."""
        item = TodoItem(content="Test task", status=TodoStatus.COMPLETED)
        assert item.to_markdown() == "[x] Test task"

    def test_todo_serialization(self):
        """TodoItem serializes and deserializes correctly."""
        item = TodoItem(content="Test", status=TodoStatus.PENDING, priority=1)
        data = item.to_dict()

        restored = TodoItem.from_dict(data)
        assert restored.content == item.content
        assert restored.status == item.status
        assert restored.priority == item.priority


class TestTodoListMiddleware:
    """Test TodoListMiddleware."""

    @pytest.mark.asyncio
    async def test_before_agent_start_loads_todos(self):
        """before_agent_start loads todos into state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))

            # Pre-save some todos
            store.save_todos("user1", "project1", [
                {"content": "Task 1", "status": "pending"},
                {"content": "Task 2", "status": "completed"},
            ])

            middleware = TodoListMiddleware(store, project_slug="project1")

            # Create state with thread_id
            state = {"thread_id": "user1", "todos": []}

            await middleware.before_agent_start(state)

            assert len(state["todos"]) == 2
            assert state["todos"][0]["content"] == "Task 1"

    @pytest.mark.asyncio
    async def test_after_agent_end_saves_todos(self):
        """after_agent_end saves todos to store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            middleware = TodoListMiddleware(store, project_slug="project1")

            # Simulate result with todos
            result = {
                "thread_id": "user1",
                "todos": [
                    {"content": "New task", "status": "pending"},
                ],
            }

            await middleware.after_agent_end(result)

            # Verify saved
            loaded = store.load_todos("user1", "project1")
            assert len(loaded) == 1
            assert loaded[0]["content"] == "New task"

    @pytest.mark.asyncio
    async def test_empty_todos_no_save(self):
        """Empty todos don't cause errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            middleware = TodoListMiddleware(store, project_slug="project1")

            result = {"thread_id": "user1", "todos": []}

            await middleware.after_agent_end(result)

            loaded = store.load_todos("user1", "project1")
            assert loaded == []


class TestPlanTools:
    """Test Plan mode tools."""

    def test_write_todo_tool_exists(self):
        """write_todo tool can be imported."""
        assert write_todo is not None
        assert write_todo.name == "write_todo"

    def test_write_todo_signature(self):
        """write_todo tool has expected parameters."""
        assert "content" in write_todo.args_schema.model_fields
        assert "status" in write_todo.args_schema.model_fields
        assert "priority" in write_todo.args_schema.model_fields

    def test_write_todo_execution(self):
        """write_todo tool returns formatted output."""
        result = write_todo.invoke({"content": "Test task", "status": "pending"})
        assert "Test task" in result
        assert "[ ] Test task" in result
        assert "todo-" in result

    def test_complete_todo_tool_exists(self):
        """complete_todo tool can be imported."""
        assert complete_todo is not None
        assert complete_todo.name == "complete_todo"

    def test_list_todos_tool_exists(self):
        """list_todos tool can be imported."""
        assert list_todos is not None
        assert list_todos.name == "list_todos"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
