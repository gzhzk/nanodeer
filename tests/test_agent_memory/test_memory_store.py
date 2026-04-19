"""Unit tests for MemoryStore — USER / L3 / episodic storage."""

import pytest
import tempfile
from datetime import date, timedelta
from pathlib import Path

from nanodeer.agent.memory.storage import MemoryStore


@pytest.fixture
def store():
    """MemoryStore with a temporary root directory."""
    with tempfile.TemporaryDirectory() as tmp:
        yield MemoryStore(root=Path(tmp))


class TestUserMemory:
    """USER.md — user preferences."""

    def test_save_and_load_user_memory(self, store):
        """Save and load user memory."""
        store.save_user_memory("I prefer concise responses.")
        result = store.load_user_memory()
        assert "I prefer concise responses" in result

    def test_load_user_memory_empty_when_no_file(self, store):
        """Returns empty string if USER.md doesn't exist."""
        assert store.load_user_memory() == ""

    def test_user_memory_frontmatter(self, store):
        """Saves with frontmatter."""
        store.save_user_memory("Test content")
        user_file = store.root / "USER.md"
        content = user_file.read_text()
        assert content.startswith("---")
        assert "name: user-memory" in content
        assert "Test content" in content


class TestGeneralMemory:
    """MEMORY.md — long-term facts."""

    def test_save_and_load_memory(self, store):
        """Save and load L3 memory."""
        store.save_memory("The project uses Python 3.13.")
        result = store.load_memory()
        assert "Python 3.13" in result

    def test_load_memory_empty_when_no_file(self, store):
        """Returns empty string if MEMORY.md doesn't exist."""
        assert store.load_memory() == ""

    def test_memory_frontmatter(self, store):
        """Saves with frontmatter."""
        store.save_memory("Test memory content")
        memory_file = store.root / "MEMORY.md"
        content = memory_file.read_text()
        assert content.startswith("---")
        assert "name: long-term-memory" in content


class TestEpisodic:
    """episodic/ — session logs."""

    def test_append_episodic(self, store):
        """Append content to today's episodic file."""
        store.append_episodic("Turn 1: User asked about X")
        today_path = store.episodic_path(date.today())
        assert today_path.exists()
        assert "Turn 1" in today_path.read_text()

    def test_append_episodic_multiple_times(self, store):
        """Appends separated by --- separator."""
        store.append_episodic("First turn")
        store.append_episodic("Second turn")
        content = store.load_episodic(date.today())
        assert "First turn" in content
        assert "Second turn" in content
        assert "---" in content

    def test_load_episodic_specific_date(self, store):
        """Load episodic for a specific date."""
        d = date.today() - timedelta(days=3)
        store.append_episodic("Old content", d=d)
        content = store.load_episodic(d)
        assert "Old content" in content

    def test_load_episodic_no_file(self, store):
        """Returns empty string for date with no file."""
        assert store.load_episodic(date(2020, 1, 1)) == ""

    def test_load_recent_episodic(self, store):
        """Loads yesterday and today combined."""
        yesterday = date.today() - timedelta(days=1)
        store.append_episodic("Today", d=date.today())
        store.append_episodic("Yesterday", d=yesterday)
        content = store.load_recent_episodic()
        assert "Today" in content
        assert "Yesterday" in content

    def test_list_episodic(self, store):
        """Lists all dates with episodic files."""
        d1 = date.today()
        d2 = date.today() - timedelta(days=5)
        store.append_episodic("today", d=d1)
        store.append_episodic("old", d=d2)
        dates = store.list_episodic()
        assert d1 in dates
        assert d2 in dates

    def test_append_episodic_empty_content(self, store):
        """Empty content is ignored."""
        store.append_episodic("")
        assert not store.episodic_path(date.today()).exists()


class TestLoadForPrompt:
    """load_for_prompt — combined output for builder."""

    def test_load_for_prompt_order(self, store):
        """Returns USER → L3 → episodic."""
        store.save_user_memory("User preference content")
        store.save_memory("Long-term memory content")
        store.append_episodic("Episodic content")
        content = store.load_for_prompt()
        # Check order: USER first
        assert content.index("User preference") < content.index("Long-term memory")
        assert content.index("Long-term memory") < content.index("Episodic")

    def test_load_for_prompt_with_tags(self, store):
        """Output is tagged with <user_memory>, <memory>, <episodic>."""
        store.save_user_memory("user")
        store.save_memory("memory")
        store.append_episodic("episodic")
        content = store.load_for_prompt()
        assert "<user_memory>" in content
        assert "<memory>" in content
        assert "<episodic>" in content

    def test_load_for_prompt_empty_when_no_files(self, store):
        """Returns empty string when nothing stored."""
        assert store.load_for_prompt() == ""
