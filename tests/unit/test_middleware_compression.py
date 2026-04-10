"""Unit tests for CompressionMiddleware."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from nanodeer.agent.middlewares.compression import CompressionMiddleware
from nanodeer.agent.state import ThreadState


class TestCompressionMiddleware:
    """Test CompressionMiddleware message compression."""

    def setup_method(self):
        self.mw = CompressionMiddleware()

    def test_init_defaults(self):
        """Default threshold and keep_recent."""
        assert self.mw.threshold == 20
        assert self.mw.keep_recent == 5
        assert self.mw._llm is None

    def test_init_custom_values(self):
        """Custom threshold and keep_recent."""
        mw = CompressionMiddleware(threshold=10, keep_recent=3)
        assert mw.threshold == 10
        assert mw.keep_recent == 3

    def test_set_llm(self):
        """set_llm updates the LLM."""
        mock_llm = MagicMock()
        self.mw.set_llm(mock_llm)
        assert self.mw.llm is mock_llm

    def test_llm_property_raises_when_none(self):
        """llm property raises if not set."""
        mw = CompressionMiddleware()
        with pytest.raises(RuntimeError, match="llm not set"):
            _ = mw.llm

    @pytest.mark.asyncio
    async def test_no_compression_below_threshold(self):
        """No compression when messages below threshold."""
        mw = CompressionMiddleware(threshold=20)
        state = MagicMock(spec=ThreadState)
        state.messages = [HumanMessage(content=f"msg {i}") for i in range(10)]

        await mw.before_agent_start(state)
        # Messages unchanged
        assert len(state.messages) == 10

    @pytest.mark.asyncio
    async def test_compression_merges_old_messages(self):
        """Messages above threshold are compressed into one."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="Summarized conversation"))
        mw = CompressionMiddleware(threshold=5, keep_recent=2, llm=mock_llm)

        messages = [
            HumanMessage(content="msg 1"),
            AIMessage(content="msg 2"),
            HumanMessage(content="msg 3"),
            AIMessage(content="msg 4"),
            HumanMessage(content="msg 5"),
            HumanMessage(content="msg 6"),  # 6 messages, above threshold 5
        ]
        state = MagicMock(spec=ThreadState)
        state.messages = messages

        await mw.before_agent_start(state)

        # Should compress to 1 summary + 2 recent
        assert len(state.messages) == 3
        # Last 2 messages preserved
        assert state.messages[-1].content == "msg 6"
        assert state.messages[-2].content == "msg 5"

    @pytest.mark.asyncio
    async def test_compression_replaces_with_summary(self):
        """Old messages replaced with summary SystemMessage."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="This is the summary"))
        mw = CompressionMiddleware(threshold=3, keep_recent=1, llm=mock_llm)

        state = MagicMock(spec=ThreadState)
        state.messages = [
            HumanMessage(content="msg 1"),
            AIMessage(content="msg 2"),
            HumanMessage(content="msg 3"),
            HumanMessage(content="msg 4"),  # 4 > threshold 3, triggers compression
        ]

        await mw.before_agent_start(state)

        # First message should be a summary system message
        first_msg = state.messages[0]
        assert isinstance(first_msg, SystemMessage)
        assert "This is the summary" in first_msg.content

    @pytest.mark.asyncio
    async def test_compression_keeps_recent_intact(self):
        """Last N messages are always kept."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="Summary"))
        mw = CompressionMiddleware(threshold=4, keep_recent=2, llm=mock_llm)

        state = MagicMock(spec=ThreadState)
        state.messages = [
            HumanMessage(content="old 1"),
            HumanMessage(content="old 2"),
            HumanMessage(content="recent 1"),
            HumanMessage(content="recent 2"),
        ]

        await mw.before_agent_start(state)

        # Recent messages preserved
        assert "recent 1" in state.messages[-2].content
        assert "recent 2" in state.messages[-1].content

    @pytest.mark.asyncio
    async def test_compression_handles_dict_state(self):
        """Handles state as dict."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="Summary"))
        mw = CompressionMiddleware(threshold=3, keep_recent=1, llm=mock_llm)

        state = {"messages": [
            HumanMessage(content="msg 1"),
            AIMessage(content="msg 2"),
            HumanMessage(content="msg 3"),
            HumanMessage(content="msg 4"),  # 4 > threshold 3, 3 summarized, 1 recent
        ]}

        await mw.before_agent_start(state)

        # 1 summary + 1 recent = 2 messages
        assert len(state["messages"]) == 2
        assert "Summary" in state["messages"][0].content

    @pytest.mark.asyncio
    async def test_compression_llm_failure_keeps_original(self):
        """If LLM summarization fails, original messages preserved."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))
        mw = CompressionMiddleware(threshold=3, keep_recent=1, llm=mock_llm)

        messages = [
            HumanMessage(content="msg 1"),
            AIMessage(content="msg 2"),
            HumanMessage(content="msg 3"),
        ]
        state = MagicMock(spec=ThreadState)
        state.messages = messages

        await mw.before_agent_start(state)

        # Should not compress - original messages preserved
        assert len(state.messages) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
