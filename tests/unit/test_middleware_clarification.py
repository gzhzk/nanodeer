"""Unit tests for ClarificationMiddleware."""
import pytest
from unittest.mock import MagicMock

from nanodeer.agent.middlewares.clarification import ClarificationMiddleware


class TestClarificationMiddleware:
    """Test ClarificationMiddleware."""

    def setup_method(self):
        self.mw = ClarificationMiddleware()

    @pytest.mark.asyncio
    async def test_passes_through_non_clarification_tools(self):
        """Non-ask_clarification tools pass through unchanged."""
        state = MagicMock()
        result = "some tool result"
        output = await self.mw.after_tool_call(state, "bash", {"command": "ls"}, result)
        assert output == result

    @pytest.mark.asyncio
    async def test_blocks_empty_question(self):
        """ask_clarification without question returns error."""
        state = MagicMock()
        result = await self.mw.after_tool_call(state, "ask_clarification", {"question": ""}, "placeholder")
        assert "Error" in result
        assert "required" in result.lower()

    @pytest.mark.asyncio
    async def test_sets_needs_clarification_true(self):
        """Sets state.needs_clarification = True."""
        state = MagicMock()
        await self.mw.after_tool_call(state, "ask_clarification", {"question": "What file?"}, "placeholder")
        assert state.needs_clarification is True

    @pytest.mark.asyncio
    async def test_sets_needs_clarification_dict(self):
        """Sets state['needs_clarification'] = True for dict state."""
        state = {"needs_clarification": False}
        await self.mw.after_tool_call(state, "ask_clarification", {"question": "What file?"}, "placeholder")
        assert state["needs_clarification"] is True

    @pytest.mark.asyncio
    async def test_response_contains_question(self):
        """Response contains the question."""
        state = MagicMock()
        result = await self.mw.after_tool_call(
            state, "ask_clarification", {"question": "Which file to edit?"}, "placeholder"
        )
        assert "Which file to edit?" in result

    @pytest.mark.asyncio
    async def test_response_contains_type(self):
        """Response contains clarification_type."""
        state = MagicMock()
        result = await self.mw.after_tool_call(
            state, "ask_clarification",
            {"question": "Continue?", "clarification_type": "confirm"},
            "placeholder"
        )
        assert "confirm" in result

    @pytest.mark.asyncio
    async def test_response_with_options(self):
        """Response includes options when provided."""
        state = MagicMock()
        result = await self.mw.after_tool_call(
            state, "ask_clarification",
            {"question": "Which option?", "options": ["Option A", "Option B"]},
            "placeholder"
        )
        assert "Option A" in result
        assert "Option B" in result

    @pytest.mark.asyncio
    async def test_response_with_context(self):
        """Response includes context when provided."""
        state = MagicMock()
        result = await self.mw.after_tool_call(
            state, "ask_clarification",
            {"question": "Confirm?", "context": "File was modified"},
            "placeholder"
        )
        assert "File was modified" in result

    @pytest.mark.asyncio
    async def test_waits_for_user_message(self):
        """Response contains waiting message."""
        state = MagicMock()
        result = await self.mw.after_tool_call(
            state, "ask_clarification", {"question": "Continue?"}, "placeholder"
        )
        assert "Waiting" in result or "user" in result.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
