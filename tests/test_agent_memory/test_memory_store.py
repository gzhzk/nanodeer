"""Tests for MemoryStore — flat-file memory (USER.md + MEMORY.md).

Episodic, wiki, and frontmatter tests removed in v0.2 — those features
moved to extension modules (wiki.py, layers.py).
"""

import pytest
import tempfile
from pathlib import Path

from nanodeer.agent.memory.storage import MemoryStore


@pytest.fixture
def store():
    """MemoryStore with a temporary root directory."""
    with tempfile.TemporaryDirectory() as tmp:
        yield MemoryStore(root=Path(tmp))


class TestUserMemory:
    def test_save_and_load_user_memory(self, store):
        """Save and load user memory."""
        store.save_user_memory("I prefer concise responses.")
        result = store.load_user_memory()
        assert "I prefer concise responses" in result

    def test_load_user_memory_empty_when_no_file(self, store):
        """Returns empty string if USER.md doesn't exist."""
        assert store.load_user_memory() == ""


class TestGeneralMemory:
    def test_save_and_load_memory(self, store):
        """Save and load general memory."""
        store.save_memory("The project uses Python 3.13.")
        result = store.load_memory()
        assert "Python 3.13" in result

    def test_load_memory_empty_when_no_file(self, store):
        """Returns empty string if MEMORY.md doesn't exist."""
        assert store.load_memory() == ""

    def test_save_memory_append_mode(self, store):
        """Append mode adds to existing content."""
        store.save_memory("First note.")
        store.save_memory("Second note.")
        result = store.load_memory()
        assert "First note." in result
        assert "Second note." in result

    def test_save_memory_replace_mode(self, store):
        """Replace mode overwrites existing content."""
        store.save_memory("First note.")
        store.save_memory("Replacement.", mode="replace")
        result = store.load_memory()
        assert "First note" not in result
        assert "Replacement." in result


class TestLoadForPrompt:
    def test_load_for_prompt_returns_both(self, store):
        """load_for_prompt returns USER.md + MEMORY.md tagged."""
        store.save_user_memory("User: likes Python")
        store.save_memory("Project: NanoDeer")
        result = store.load_for_prompt()
        assert "<user_memory>" in result
        assert "likes Python" in result
        assert "<memory>" in result
        assert "NanoDeer" in result

    def test_load_for_prompt_empty_when_no_memory(self, store):
        """Returns empty string when no memory saved."""
        assert store.load_for_prompt() == ""
