"""Unit tests for MemoryMiddleware."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import date
from langchain_core.messages import HumanMessage, AIMessage

from nanodeer.agent.middlewares.memory import MemoryMiddleware
from nanodeer.agent.state import ThreadState
from nanodeer.agent.memory.types import EpisodicEntry


class TestMemoryMiddleware:
    """Test MemoryMiddleware L2/L3 memory management."""

    def setup_method(self):
        self.store = MagicMock()
        self.extractor = MagicMock()
        self.mw = MemoryMiddleware(memory_store=self.store, extractor=self.extractor, auto_extract=True)

    def test_init_auto_extract_true(self):
        """auto_extract defaults to True."""
        mw = MemoryMiddleware(memory_store=self.store)
        assert mw.auto_extract is True

    def test_init_auto_extract_false(self):
        """auto_extract can be set to False."""
        mw = MemoryMiddleware(memory_store=self.store, auto_extract=False)
        assert mw.auto_extract is False

    @pytest.mark.asyncio
    async def test_before_agent_start_loads_memory(self):
        """Loads memory context into state."""
        self.store.load.return_value = "<memory>\nSome memory\n</memory>"
        self.store.load_project_memory.return_value = ""

        state = MagicMock(spec=ThreadState)
        state.project_slug = None
        state.memory_context = None
        await self.mw.before_agent_start(state)
        assert state.memory_context is not None
        assert "Some memory" in state.memory_context

    @pytest.mark.asyncio
    async def test_before_agent_start_combines_project_memory(self):
        """Combines L3 and project memory."""
        self.store.load.return_value = "<memory>\nGlobal memory\n</memory>"
        self.store.load_project_memory.return_value = "Project specific memory"

        state = MagicMock(spec=ThreadState)
        state.project_slug = "my-project"
        state.memory_context = None
        await self.mw.before_agent_start(state)
        assert "Global memory" in state.memory_context
        assert "Project specific memory" in state.memory_context

    @pytest.mark.asyncio
    async def test_after_agent_end_skips_when_disabled(self):
        """Skips episodic write when auto_extract is False."""
        mw = MemoryMiddleware(memory_store=self.store, auto_extract=False)
        state = MagicMock(spec=ThreadState)
        state.messages = [HumanMessage(content="hello")]
        await mw.after_agent_end(state)
        self.store.save_episodic.assert_not_called()

    @pytest.mark.asyncio
    async def test_after_agent_end_saves_episodic(self):
        """Saves episodic entry after agent ends."""
        state = MagicMock(spec=ThreadState)
        state.messages = [
            HumanMessage(content="User request"),
            AIMessage(content="Agent response"),
        ]

        await self.mw.after_agent_end(state)
        self.store.save_episodic.assert_called_once()
        # Verify it's called with markdown content
        call_args = self.store.save_episodic.call_args[0][0]
        assert "User request" in call_args

    @pytest.mark.asyncio
    async def test_after_agent_end_no_messages(self):
        """Skips episodic when no messages."""
        state = MagicMock(spec=ThreadState)
        state.messages = []
        await self.mw.after_agent_end(state)
        self.store.save_episodic.assert_not_called()

    @pytest.mark.asyncio
    async def test_distill_triggered_when_should_distill(self):
        """Distillation is triggered when should_distill returns True."""
        self.store.should_distill.return_value = True
        self.extractor.distill = AsyncMock(return_value="Distilled content")
        # _distill requires at least 3 episodic files
        self.store.list_episodic.return_value = [date.today(), date.today(), date.today()]
        self.store.load_episodic.return_value = "Some episodic content"

        state = MagicMock(spec=ThreadState)
        state.messages = [HumanMessage(content="hello")]
        await self.mw.after_agent_end(state)
        self.extractor.distill.assert_called_once()

    @pytest.mark.asyncio
    async def test_after_tool_call_passthrough_non_save_memory(self):
        """Non-save_memory tools pass through unchanged."""
        state = MagicMock(spec=ThreadState)
        result = "bash result"
        output = await self.mw.after_tool_call(state, "bash", {}, result)
        assert output == result

    @pytest.mark.asyncio
    async def test_after_tool_call_save_memory_user(self):
        """Intercepts save_memory and stores in user memory."""
        state = MagicMock(spec=ThreadState)
        tool_args = {"content": "Important info", "category": "user"}
        result = "saved"
        output = await self.mw.after_tool_call(state, "save_memory", tool_args, result)
        self.store.save_memory.assert_called_once_with("Important info")
        assert output == result

    @pytest.mark.asyncio
    async def test_after_tool_call_save_memory_project(self):
        """Intercepts save_memory with project and stores in project memory."""
        state = MagicMock(spec=ThreadState)
        tool_args = {"content": "Project info", "category": "project", "project": "my-proj"}
        result = "saved"
        output = await self.mw.after_tool_call(state, "save_memory", tool_args, result)
        self.store.save_project_memory.assert_called_once_with("my-proj", "Project info")
        assert output == result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
