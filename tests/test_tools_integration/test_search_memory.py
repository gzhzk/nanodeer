"""Tests for search_memory tool."""

from unittest.mock import MagicMock, patch

from nanodeer.tools.search_memory import search_memory


class TestSearchMemoryTool:
    def test_search_includes_flat_memory_matches(self):
        with patch("nanodeer.tools.search_memory.MemoryStore") as MockStore:
            mock_store = MagicMock()
            mock_store.search_wiki.return_value = []
            mock_store.load_memory.return_value = "Durable phrase: COMPRESS-SAFE-4242"
            mock_store.load_user_memory.return_value = ""
            MockStore.return_value = mock_store

            result = search_memory.invoke({"query": "COMPRESS-SAFE-4242"})

            assert "memory/MEMORY.md" in result
            assert "COMPRESS-SAFE-4242" in result

    def test_search_empty_when_no_wiki_or_flat_memory_matches(self):
        with patch("nanodeer.tools.search_memory.MemoryStore") as MockStore:
            mock_store = MagicMock()
            mock_store.search_wiki.return_value = []
            mock_store.load_memory.return_value = "Other memory"
            mock_store.load_user_memory.return_value = ""
            MockStore.return_value = mock_store

            result = search_memory.invoke({"query": "missing"})

            assert result == "No matching memory entries found."
