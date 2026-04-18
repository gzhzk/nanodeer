"""Tests for write_todo tool."""
import pytest
from unittest.mock import MagicMock, patch

from nanodeer.tools.write_todo import write_todo


class TestWriteTodoTool:
    def test_invoke_create(self):
        """Creating a new todo works."""
        with patch("nanodeer.tools.write_todo.TodoStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load.return_value = []
            MockStore.return_value = mock_store

            result = write_todo.invoke({
                "content": "Implement feature X",
            })

            assert "Todo added:" in result
            assert "Implement feature X" in result
            mock_store.save.assert_called_once()

    def test_invoke_create_without_content(self):
        """Creating without content returns error."""
        with patch("nanodeer.tools.write_todo.TodoStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load.return_value = []
            MockStore.return_value = mock_store

            result = write_todo.invoke({})
            assert "content is required" in result

    def test_invoke_update_existing(self):
        """Updating existing todo by ID works."""
        with patch("nanodeer.tools.write_todo.TodoStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load.return_value = [
                {"id": "test-123", "content": "Old task", "status": "pending", "priority": 0}
            ]
            MockStore.return_value = mock_store

            result = write_todo.invoke({
                "id": "test-123",
                "content": "Updated task",
                "status": "completed",
            })

            assert "Todo updated:" in result
            assert "test-123" in result

    def test_invoke_update_nonexistent(self):
        """Updating nonexistent ID returns error."""
        with patch("nanodeer.tools.write_todo.TodoStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load.return_value = []
            MockStore.return_value = mock_store

            result = write_todo.invoke({"id": "nonexistent"})
            assert "not found" in result

    def test_invoke_with_priority(self):
        """Creating with priority works."""
        with patch("nanodeer.tools.write_todo.TodoStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load.return_value = []
            MockStore.return_value = mock_store

            result = write_todo.invoke({
                "content": "Important task",
                "priority": 5,
            })

            assert "Todo added:" in result
