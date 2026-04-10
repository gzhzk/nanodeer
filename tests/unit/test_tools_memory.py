"""Unit tests for memory tools (save_memory, load_memory)."""
import pytest
import tempfile
import shutil

from nanodeer.tools.memory import save_memory, load_memory


class TestSaveMemory:
    """Test save_memory tool."""

    def test_returns_string(self):
        """save_memory returns string."""
        result = save_memory.invoke({"content": "Test memory"})
        assert isinstance(result, str)

    def test_contains_category(self):
        """Result contains category."""
        result = save_memory.invoke({"content": "Test", "category": "user"})
        assert "user" in result.lower()

    def test_contains_content_preview(self):
        """Result contains content preview."""
        result = save_memory.invoke({"content": "This is a long memory content"})
        assert "This is a" in result

    def test_project_note(self):
        """Result includes project note when project specified."""
        result = save_memory.invoke({"content": "Test", "project": "my-proj"})
        assert "my-proj" in result


class TestLoadMemory:
    """Test load_memory tool."""

    def test_returns_string(self):
        """load_memory returns string."""
        result = load_memory.invoke({})
        assert isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
