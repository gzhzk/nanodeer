"""Tests for list_todos tool."""
import pytest
from unittest.mock import MagicMock, patch

from nanodeer.tools.list_todos import list_todos


class TestListTodosTool:
    def test_invoke_empty(self):
        """Empty todos returns '(no todos)'."""
        with patch("nanodeer.tools.list_todos.TodoStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load.return_value = []
            MockStore.return_value = mock_store

            result = list_todos.invoke({})
            assert result == "(no todos)"

    def test_invoke_with_todos(self):
        """Returns formatted list of todos."""
        with patch("nanodeer.tools.list_todos.TodoStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load.return_value = [
                {"id": "id-1", "content": "Task 1", "status": "pending", "priority": 0},
                {"id": "id-2", "content": "Task 2", "status": "completed", "priority": 0},
            ]
            MockStore.return_value = mock_store

            result = list_todos.invoke({})

            assert "[ ] Task 1" in result
            assert "[x] Task 2" in result
            assert "id=id-1" in result
            assert "id=id-2" in result

    def test_invoke_in_progress_uses_asterisk(self):
        """in_progress status shows [*]."""
        with patch("nanodeer.tools.list_todos.TodoStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load.return_value = [
                {"id": "id-1", "content": "Running task", "status": "in_progress", "priority": 0},
            ]
            MockStore.return_value = mock_store

            result = list_todos.invoke({})

            assert "[*] Running task" in result
            assert "id=id-1" in result
