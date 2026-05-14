"""Tests for save_memory tool."""
import pytest
from unittest.mock import MagicMock, patch

from nanodeer.tools.save_memory import save_memory


class TestSaveMemoryTool:
    def test_invoke_default_saves_to_memory(self):
        """Save to MEMORY.md by default."""
        with patch("nanodeer.tools.save_memory.MemoryStore") as MockStore:
            mock_store = MagicMock()
            MockStore.return_value = mock_store

            result = save_memory.invoke({
                "target": "memory",
                "content": "User prefers dark mode and uses VSCode as primary editor, typically works on Python projects."
            })

            assert "Memory saved:" in result
            mock_store.save_memory.assert_called_once()

    def test_invoke_target_user_saves_to_user_memory(self):
        """Save to USER.md when target='user'."""
        with patch("nanodeer.tools.save_memory.MemoryStore") as MockStore:
            mock_store = MagicMock()
            MockStore.return_value = mock_store

            result = save_memory.invoke({
                "content": "User prefers dark mode",
                "target": "user",
            })

            assert "User memory saved:" in result
            mock_store.save_user_memory.assert_called_once()

    def test_invoke_truncates_long_content(self):
        """Long content is truncated in response."""
        with patch("nanodeer.tools.save_memory.MemoryStore") as MockStore:
            mock_store = MagicMock()
            MockStore.return_value = mock_store

            long_content = "This is a very long content string that exceeds two hundred characters in length. " * 5
            result = save_memory.invoke({"target": "memory", "content": long_content})

            assert "..." in result  # truncated

    def test_invoke_short_content_not_truncated(self):
        """Short content is not truncated."""
        with patch("nanodeer.tools.save_memory.MemoryStore") as MockStore:
            mock_store = MagicMock()
            MockStore.return_value = mock_store

            result = save_memory.invoke({"target": "memory", "content": "Short note for memory"})
            assert "..." not in result
            assert "Short note for memory" in result
