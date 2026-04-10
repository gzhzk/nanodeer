"""Unit tests for TitleMiddleware."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from langchain_core.messages import HumanMessage, AIMessage

from nanodeer.agent.middlewares.title import TitleMiddleware
from nanodeer.agent.state import ThreadState


class TestTitleMiddleware:
    """Test TitleMiddleware title generation."""

    def setup_method(self):
        self.mw = TitleMiddleware()

    def test_init_defaults(self):
        """Default max_length is 50."""
        assert self.mw.max_length == 50
        assert self.mw._llm is None

    def test_init_custom_llm(self):
        """Custom LLM at init."""
        mock_llm = MagicMock()
        mw = TitleMiddleware(llm=mock_llm)
        assert mw.llm is mock_llm

    def test_init_custom_max_length(self):
        """Custom max_length."""
        mw = TitleMiddleware(max_length=30)
        assert mw.max_length == 30

    def test_set_llm(self):
        """set_llm updates the LLM."""
        mock_llm = MagicMock()
        self.mw.set_llm(mock_llm)
        assert self.mw.llm is mock_llm

    def test_llm_property_raises_when_none(self):
        """llm property raises if not set."""
        with pytest.raises(RuntimeError, match="llm not set"):
            _ = self.mw.llm

    @pytest.mark.asyncio
    async def test_skips_when_llm_not_set(self):
        """No-op when LLM not set."""
        state = MagicMock(spec=ThreadState)
        state.title = None
        state.thread_id = "test"
        state.messages = [HumanMessage(content="Hello")]

        await self.mw.after_agent_end(state)
        # Should not raise

    @pytest.mark.asyncio
    async def test_skips_when_title_already_set(self):
        """Skips if title already exists."""
        mock_llm = MagicMock()
        state = MagicMock(spec=ThreadState)
        state.title = "Existing Title"
        state.thread_id = "test"
        state.messages = [HumanMessage(content="Hello")]

        await self.mw.after_agent_end(state)
        # LLM should not be called
        mock_llm.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_generates_title_from_first_user_message(self):
        """Generates title from first HumanMessage."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="Test Title"))
        mw = TitleMiddleware(llm=mock_llm)

        state = MagicMock(spec=ThreadState)
        state.title = None
        state.thread_id = "test"
        state.messages = [
            HumanMessage(content="Help me write a script"),
            AIMessage(content="I'll help you write a script"),
        ]

        await mw.after_agent_end(state)

        assert state.title == "Test Title"
        mock_llm.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_truncates_title_to_max_length(self):
        """Truncates title to max_length."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="This is a very long title that should be truncated"))
        mw = TitleMiddleware(llm=mock_llm, max_length=20)

        state = MagicMock(spec=ThreadState)
        state.title = None
        state.thread_id = "test"
        state.messages = [HumanMessage(content="Hello")]

        await mw.after_agent_end(state)

        assert len(state.title) <= 20

    @pytest.mark.asyncio
    async def test_fallback_uses_first_message_when_llm_fails(self):
        """Falls back to truncating first message when LLM fails."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))
        mw = TitleMiddleware(llm=mock_llm, max_length=50)

        state = MagicMock(spec=ThreadState)
        state.title = None
        state.thread_id = "test"
        state.messages = [HumanMessage(content="Help me with my Python project")]

        await mw.after_agent_end(state)

        assert "Help me with my Python project" in state.title
        assert len(state.title) <= 50

    @pytest.mark.asyncio
    async def test_handles_dict_state(self):
        """Handles state as dict."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="Dict Title"))
        mw = TitleMiddleware(llm=mock_llm)

        state = {
            "title": None,
            "thread_id": "test",
            "messages": [HumanMessage(content="Hello")],
        }

        await mw.after_agent_end(state)

        assert state["title"] == "Dict Title"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
