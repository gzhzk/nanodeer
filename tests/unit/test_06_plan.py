"""Unit tests for Plan/Todo system."""
import pytest
from harness.plan import TodoItem, TodoStatus


class TestTodoItem:
    """Test TodoItem data structure."""

    def test_todo_creation(self):
        """TodoItem creates with defaults."""
        item = TodoItem(content="Test task")
        assert item.content == "Test task"
        assert item.status == TodoStatus.PENDING
        assert item.priority == 0
        assert item.id.startswith("todo-")

    def test_todo_with_all_fields(self):
        """TodoItem with all fields."""
        item = TodoItem(
            content="Important task",
            status=TodoStatus.IN_PROGRESS,
            priority=5,
        )
        assert item.content == "Important task"
        assert item.status == TodoStatus.IN_PROGRESS
        assert item.priority == 5

    def test_to_markdown_pending(self):
        """Pending todo shows [ ]."""
        item = TodoItem(content="Task", status=TodoStatus.PENDING)
        assert item.to_markdown() == "[ ] Task"

    def test_to_markdown_in_progress(self):
        """In progress todo shows [>]."""
        item = TodoItem(content="Task", status=TodoStatus.IN_PROGRESS)
        assert item.to_markdown() == "[>] Task"

    def test_to_markdown_completed(self):
        """Completed todo shows [x]."""
        item = TodoItem(content="Task", status=TodoStatus.COMPLETED)
        assert item.to_markdown() == "[x] Task"

    def test_to_dict(self):
        """TodoItem serializes to dict."""
        item = TodoItem(content="Test", status=TodoStatus.PENDING, priority=1)
        data = item.to_dict()

        assert data["content"] == "Test"
        assert data["status"] == "pending"
        assert data["priority"] == 1
        assert "id" in data

    def test_from_dict(self):
        """TodoItem deserializes from dict."""
        data = {
            "id": "todo-123",
            "content": "Restored task",
            "status": "completed",
            "priority": 2,
        }
        item = TodoItem.from_dict(data)

        assert item.id == "todo-123"
        assert item.content == "Restored task"
        assert item.status == TodoStatus.COMPLETED
        assert item.priority == 2

    def test_roundtrip(self):
        """Serialize and deserialize preserves data."""
        item = TodoItem(content="Roundtrip", status=TodoStatus.IN_PROGRESS, priority=3)
        data = item.to_dict()
        restored = TodoItem.from_dict(data)

        assert restored.content == item.content
        assert restored.status == item.status
        assert restored.priority == item.priority
        assert restored.id == item.id


class TestTodoStatus:
    """Test TodoStatus enum."""

    def test_status_values(self):
        """Status has correct string values."""
        assert TodoStatus.PENDING.value == "pending"
        assert TodoStatus.IN_PROGRESS.value == "in_progress"
        assert TodoStatus.COMPLETED.value == "completed"

    def test_status_from_string(self):
        """Can create status from string."""
        assert TodoStatus("pending") == TodoStatus.PENDING
        assert TodoStatus("in_progress") == TodoStatus.IN_PROGRESS
        assert TodoStatus("completed") == TodoStatus.COMPLETED

    def test_invalid_status(self):
        """Invalid status string raises error."""
        with pytest.raises(ValueError):
            TodoStatus("invalid")


class TestTodoListMiddlewareMock:
    """Test TodoListMiddleware with mocked store."""

    @pytest.mark.asyncio
    async def test_before_agent_start_loads_todos(self):
        """before_agent_start loads todos into state."""
        from harness.middlewares import TodoListMiddleware
        import tempfile
        from pathlib import Path
        from harness.memory import MemoryStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))

            # Pre-save some todos
            store.save_todos("user1", "project1", [
                {"content": "Task 1", "status": "pending"},
                {"content": "Task 2", "status": "completed"},
            ])

            middleware = TodoListMiddleware(store, project_slug="project1")

            state = {"thread_id": "user1", "todos": []}
            await middleware.before_agent_start(state)

            assert len(state["todos"]) == 2
            assert state["todos"][0]["content"] == "Task 1"

    @pytest.mark.asyncio
    async def test_after_agent_end_saves_todos(self):
        """after_agent_end saves todos to store."""
        from harness.middlewares import TodoListMiddleware
        import tempfile
        from pathlib import Path
        from harness.memory import MemoryStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            middleware = TodoListMiddleware(store, project_slug="project1")

            result = {
                "thread_id": "user1",
                "todos": [
                    {"content": "New task", "status": "pending"},
                ],
            }

            await middleware.after_agent_end(result)

            loaded = store.load_todos("user1", "project1")
            assert len(loaded) == 1
            assert loaded[0]["content"] == "New task"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
