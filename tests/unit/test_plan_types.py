"""Unit tests for plan types."""
import pytest

from nanodeer.plan.types import TodoItem, TodoStatus, TODOS_SECTION_TEMPLATE


class TestTodoItem:
    """Test TodoItem creation and methods."""

    def test_create_todo(self):
        """TodoItem with required fields."""
        item = TodoItem(content="Write tests")
        assert item.content == "Write tests"
        assert item.status == TodoStatus.PENDING
        assert item.id is not None

    def test_create_with_priority(self):
        """TodoItem with priority."""
        item = TodoItem(content="Important task", priority=5)
        assert item.priority == 5

    def test_todo_status_enum(self):
        """TodoStatus has expected values."""
        assert TodoStatus.PENDING.value == "pending"
        assert TodoStatus.IN_PROGRESS.value == "in_progress"
        assert TodoStatus.COMPLETED.value == "completed"

    def test_to_markdown(self):
        """to_markdown returns formatted string."""
        item = TodoItem(content="Test task")
        md = item.to_markdown()
        assert "Test task" in md
        assert "[ ]" in md  # pending icon

    def test_from_dict(self):
        """from_dict recreates TodoItem."""
        d = {
            "id": "test-id",
            "content": "From dict",
            "status": "completed",
            "priority": 3
        }
        item = TodoItem.from_dict(d)
        assert item.id == "test-id"
        assert item.content == "From dict"
        assert item.status == TodoStatus.COMPLETED
        assert item.priority == 3

    def test_to_dict(self):
        """to_dict returns serializable dict."""
        item = TodoItem(content="Serialize me")
        d = item.to_dict()
        assert isinstance(d, dict)
        assert d["content"] == "Serialize me"
        assert d["status"] == "pending"
        assert "id" in d


class TestTodosSectionTemplate:
    """Test todo section template."""

    def test_template_exists(self):
        """TODOS_SECTION_TEMPLATE is defined."""
        assert TODOS_SECTION_TEMPLATE is not None
        assert "{todos}" in TODOS_SECTION_TEMPLATE or "todos" in TODOS_SECTION_TEMPLATE.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
