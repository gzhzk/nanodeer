"""Unit tests for MemoryStore file-based storage."""
import pytest
import tempfile
from pathlib import Path

from harness.memory import MemoryEntry, MemoryStore
from harness.memory.storage import USER_MEMORY_FILE, PROJECT_DIR


class TestMemoryEntry:
    """Test MemoryEntry serialization."""

    def test_to_frontmatter(self):
        """MemoryEntry serializes to frontmatter."""
        entry = MemoryEntry(
            name="test_memory",
            description="A test entry",
            memory_type="user",
            content="Test content here.",
        )

        result = entry.to_frontmatter()

        assert "name: test_memory" in result
        assert "description: A test entry" in result
        assert "type: user" in result
        assert "Test content here." in result

    def test_from_frontmatter(self):
        """MemoryEntry parses from frontmatter."""
        raw = """---
name: test_memory
description: A test entry
type: user
updated: 2024-01-01T00:00:00
---

Test content here.
Second line.
"""
        entry = MemoryEntry.from_frontmatter(raw)

        assert entry.name == "test_memory"
        assert entry.description == "A test entry"
        assert entry.memory_type == "user"
        assert entry.content == "Test content here.\nSecond line."

    def test_roundtrip(self):
        """Serialize and deserialize preserves data."""
        entry = MemoryEntry(
            name="roundtrip_test",
            description="Testing roundtrip",
            memory_type="project",
            content="Some content.",
        )

        serialized = entry.to_frontmatter()
        restored = MemoryEntry.from_frontmatter(serialized)

        assert restored.name == entry.name
        assert restored.description == entry.description
        assert restored.memory_type == entry.memory_type
        assert restored.content == entry.content


class TestMemoryStore:
    """Test MemoryStore file operations."""

    def test_load_user_memory_empty(self):
        """Returns empty string when user memory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            result = store.load_user_memory("nonexistent_user")
            assert result == ""

    def test_save_and_load_user_memory(self):
        """Saves and loads user memory correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            store.save_user_memory(
                user_id="test_user",
                content="I prefer concise responses.",
                name="user_preference",
                description="User likes concise replies",
            )

            user_dir = Path(tmpdir) / "test_user"
            assert (user_dir / USER_MEMORY_FILE).exists()

            result = store.load_user_memory("test_user")
            assert "I prefer concise responses." in result

    def test_save_and_load_project_memory(self):
        """Saves and loads project memory correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            store.save_project_memory(
                user_id="test_user",
                project_slug="my_project",
                content="This project uses Python.",
                name="project_info",
                description="Project tech stack",
            )

            user_dir = Path(tmpdir) / "test_user"
            project_dir = user_dir / PROJECT_DIR
            assert (project_dir / "my_project.md").exists()

            result = store.load_project_memory("test_user", "my_project")
            assert "This project uses Python." in result

    def test_load_combines_user_and_project(self):
        """load() combines user and project memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            store.save_user_memory("user1", "User preference content.")
            store.save_project_memory("user1", "proj1", "Project content.")

            result = store.load("user1", "proj1")

            assert "User preference content." in result
            assert "Project content." in result
            assert "<user_memory>" in result
            assert "<project_memory>" in result

    def test_load_user_only(self):
        """load() works with only user memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            store.save_user_memory("user1", "User only content.")

            result = store.load("user1", "nonexistent_project")

            assert "User only content." in result
            assert "<user_memory>" in result
            assert "<project_memory>" not in result

    def test_load_project_only(self):
        """load() works with only project memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            store.save_project_memory("user1", "proj1", "Project only content.")

            result = store.load("user1", "proj1")

            assert "Project only content." in result
            assert "<project_memory>" in result
            assert "<user_memory>" not in result

    def test_load_returns_empty_when_nothing_exists(self):
        """load() returns empty string when nothing exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            result = store.load("brand_new_user", "brand_new_project")
            assert result == ""

    def test_user_id_sanitization(self):
        """user_id with special characters is sanitized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            store.save_user_memory("user@email.com", "Content.")

            assert store.load_user_memory("user@email.com") == "Content."

    def test_project_slug_sanitization(self):
        """project_slug with special characters is sanitized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            store.save_project_memory("user1", "my-project_v2", "Content.")

            assert store.load_project_memory("user1", "my-project_v2") == "Content."

    def test_exists(self):
        """exists() returns correct boolean."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))

            assert store.exists("user1") is False

            store.save_user_memory("user1", "Content.")
            assert store.exists("user1") is True

            store.save_project_memory("user1", "proj1", "Content.")
            assert store.exists("user1", "proj1") is True

    def test_root_creation(self):
        """MemoryStore creates root directory on init."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "new_memory_root"
            store = MemoryStore(root=root)
            assert root.exists()


class TestMemoryExtractorMock:
    """Test MemoryExtractor with mocked LLM."""

    @pytest.mark.asyncio
    async def test_extract_parses_json_response(self):
        """Extractor parses valid JSON from LLM response."""
        from harness.memory.extractor import MemoryExtractor
        from unittest.mock import AsyncMock, MagicMock

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '''[{
            "name": "User prefers Python",
            "description": "User likes Python",
            "category": "user",
            "content": "Always use Python",
            "keywords": ["python"]
        }]'''
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        extractor = MemoryExtractor(mock_llm)

        from langchain_core.messages import HumanMessage, AIMessage
        messages = [
            HumanMessage(content="I want to build a web app"),
            AIMessage(content="I'll use Python with FastAPI"),
        ]

        result = await extractor.extract(messages)

        assert len(result) == 1
        assert result[0].name == "User prefers Python"
        assert result[0].category == "user"

    @pytest.mark.asyncio
    async def test_extract_handles_invalid_json(self):
        """Extractor handles non-JSON LLM response gracefully."""
        from harness.memory.extractor import MemoryExtractor
        from unittest.mock import AsyncMock, MagicMock

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "This is not JSON"
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        extractor = MemoryExtractor(mock_llm)

        from langchain_core.messages import HumanMessage
        messages = [HumanMessage(content="Hello")]

        result = await extractor.extract(messages)
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_returns_empty_for_empty_messages(self):
        """Extractor returns empty list for empty messages."""
        from harness.memory.extractor import MemoryExtractor
        from unittest.mock import AsyncMock

        mock_llm = AsyncMock()
        extractor = MemoryExtractor(mock_llm)

        result = await extractor.extract([])
        assert result == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
