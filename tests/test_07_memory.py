"""Test 07: Memory - file-based memory storage and middleware."""

import tempfile
from pathlib import Path

import pytest

from harness.memory import MemoryEntry, MemoryStore
from harness.memory.storage import USER_MEMORY_FILE, PROJECT_DIR


class TestMemoryEntry:
    """Test MemoryEntry frontmatter serialization."""

    def test_to_frontmatter(self):
        """MemoryEntry serializes to frontmatter format."""
        entry = MemoryEntry(
            name="user_preference_terse",
            description="user wants concise responses without summaries",
            memory_type="user",
            content="Rule: no trailing summaries after tasks.\nWhy: user finds it annoying.\nHow: keep responses short.",
        )

        result = entry.to_frontmatter()

        assert "name: user_preference_terse" in result
        assert "description: user wants concise responses without summaries" in result
        assert "type: user" in result
        assert "Rule: no trailing summaries after tasks." in result

    def test_from_frontmatter(self):
        """MemoryEntry parses from frontmatter format."""
        raw = """---
name: test_memory
description: a test entry
type: project
updated: 2024-01-01T00:00:00
---

This is the content.
Second line.
"""
        entry = MemoryEntry.from_frontmatter(raw)

        assert entry.name == "test_memory"
        assert entry.description == "a test entry"
        assert entry.memory_type == "project"
        assert entry.updated_at == "2024-01-01T00:00:00"
        assert entry.content == "This is the content.\nSecond line."

    def test_roundtrip(self):
        """Serialize and deserialize preserves data."""
        entry = MemoryEntry(
            name="roundtrip_test",
            description="testing roundtrip serialization",
            memory_type="user",
            content="Some content here.",
        )

        serialized = entry.to_frontmatter()
        restored = MemoryEntry.from_frontmatter(serialized)

        assert restored.name == entry.name
        assert restored.description == entry.description
        assert restored.memory_type == entry.memory_type
        assert restored.content == entry.content


class TestMemoryStore:
    """Test MemoryStore file-based storage."""

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
                description="user likes concise replies",
            )

            user_dir = Path(tmpdir) / "test_user"
            assert (user_dir / USER_MEMORY_FILE).exists()

            result = store.load_user_memory("test_user")
            assert "I prefer concise responses." in result

    def test_load_project_memory_empty(self):
        """Returns empty string when project memory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            result = store.load_project_memory("user1", "nonexistent_project")
            assert result == ""

    def test_save_and_load_project_memory(self):
        """Saves and loads project memory correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            store.save_project_memory(
                user_id="test_user",
                project_slug="my_project",
                content="This project uses Python + LangGraph.",
                name="project_info",
                description="project tech stack",
            )

            user_dir = Path(tmpdir) / "test_user"
            project_dir = user_dir / PROJECT_DIR
            assert (project_dir / "my_project.md").exists()

            result = store.load_project_memory("test_user", "my_project")
            assert "This project uses Python + LangGraph." in result

    def test_load_combines_user_and_project(self):
        """load() combines user and project memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            store.save_user_memory("user1", "User preference content.")
            store.save_project_memory("user1", "proj1", "Project 1 content.")

            result = store.load("user1", "proj1")

            assert "User preference content." in result
            assert "Project 1 content." in result
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

            # Should save without error
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


class TestMemoryExtractor:
    """Test MemoryExtractor LLM-based extraction."""

    @pytest.mark.asyncio
    async def test_extract_parses_json_response(self):
        """Extractor parses valid JSON from LLM response."""
        from harness.memory.extractor import MemoryExtractor
        from unittest.mock import AsyncMock, MagicMock

        # Mock LLM that returns structured JSON
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '''[
            {
                "name": "User prefers Python",
                "description": "User likes Python over other languages",
                "category": "user",
                "content": "Always use Python for new projects",
                "keywords": ["python", "preference"]
            }
        ]'''
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
        assert "python" in result[0].keywords

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


class TestMemoryMiddlewareV2:
    """Test MemoryMiddleware v2 features."""

    @pytest.mark.asyncio
    async def test_after_tool_call_intercepts_save_memory(self):
        """after_tool_call saves memory when save_memory is called."""
        from harness.middlewares.memory import MemoryMiddleware
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            middleware = MemoryMiddleware(
                memory_store=store,
                project_slug="test-project",
            )

            # Simulate save_memory tool call
            tool_args = {
                "content": "User prefers dark mode",
                "category": "user",
            }

            await middleware.after_tool_call(
                state={"thread_id": "test-thread"},
                tool_name="save_memory",
                tool_args=tool_args,
                result="Memory saved",
            )

            # Verify memory was saved
            user_memory = store.load_user_memory("default")
            assert "User prefers dark mode" in user_memory

    @pytest.mark.asyncio
    async def test_after_tool_call_ignores_other_tools(self):
        """after_tool_call ignores non-save_memory tools."""
        from harness.middlewares.memory import MemoryMiddleware
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            middleware = MemoryMiddleware(
                memory_store=store,
                project_slug="test-project",
            )

            # Simulate ReadFile tool call
            await middleware.after_tool_call(
                state={},
                tool_name="ReadFile",
                tool_args={"file_path": "/tmp/test.txt"},
                result="file content",
            )

            # No memory should be saved
            assert store.load_user_memory("default") == ""

    @pytest.mark.asyncio
    async def test_after_agent_end_extracts_and_saves(self):
        """after_agent_end triggers extraction and saving."""
        from harness.middlewares.memory import MemoryMiddleware
        from unittest.mock import AsyncMock, MagicMock
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))

            # Create mock extractor
            mock_extractor = AsyncMock()
            from harness.memory.extractor import ExtractedMemory
            mock_extractor.extract = AsyncMock(return_value=[
                ExtractedMemory(
                    name="Test memory",
                    description="A test entry",
                    category="user",
                    content="Test content",
                    keywords=["test"],
                )
            ])

            middleware = MemoryMiddleware(
                memory_store=store,
                project_slug="test-project",
                extractor=mock_extractor,
                auto_extract=True,
            )

            # Simulate agent result
            from langchain_core.messages import HumanMessage
            result = {
                "messages": [HumanMessage(content="Build a web app")],
            }

            await middleware.after_agent_end(result)

            # Verify memory was saved
            user_memory = store.load_user_memory("default")
            assert "Test content" in user_memory

    @pytest.mark.asyncio
    async def test_after_agent_end_skips_when_disabled(self):
        """after_agent_end does nothing when auto_extract=False."""
        from harness.middlewares.memory import MemoryMiddleware
        from unittest.mock import AsyncMock
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(root=Path(tmpdir))
            mock_extractor = AsyncMock()

            middleware = MemoryMiddleware(
                memory_store=store,
                extractor=mock_extractor,
                auto_extract=False,  # Disabled
            )

            await middleware.after_agent_end({"messages": []})

            # Extractor should not have been called
            mock_extractor.extract.assert_not_called()


class TestSaveMemoryTool:
    """Test save_memory tool."""

    def test_save_memory_tool_exists(self):
        """save_memory tool can be imported."""
        from harness.tools import save_memory
        assert save_memory is not None
        assert save_memory.name == "save_memory"

    def test_save_memory_tool_signature(self):
        """save_memory tool has expected signature."""
        from harness.tools import save_memory
        # Check tool has the expected parameters
        assert "content" in save_memory.args_schema.model_fields
        assert "category" in SaveMemory.args_schema.model_fields


if __name__ == "__main__":
    pytest.main([__file__, "-v"])