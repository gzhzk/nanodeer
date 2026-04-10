"""Unit tests for SubagentMiddleware."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from langchain_core.messages import HumanMessage, AIMessage

from nanodeer.agent.middlewares.subagent import SubagentMiddleware
from nanodeer.agent.state import ThreadState


class TestSubagentMiddleware:
    """Test SubagentMiddleware subagent management."""

    def setup_method(self):
        self.mw = SubagentMiddleware()

    def test_init_defaults(self):
        """Default max_concurrent=3, timeout=900."""
        assert self.mw.max_concurrent == 3
        assert self.mw.timeout == 900
        assert self.mw._llm is None
        assert self.mw.tools == []

    def test_init_custom_values(self):
        """Custom max_concurrent and timeout."""
        mw = SubagentMiddleware(max_concurrent=5, timeout=600)
        assert mw.max_concurrent == 5
        assert mw.timeout == 600

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
    async def test_before_agent_start_initializes_tracking(self):
        """Initializes pending_subagent_tasks and subagent_results."""
        state = MagicMock(spec=ThreadState)
        # Remove the default empty list so we can verify initialization
        del state.pending_subagent_tasks
        del state.subagent_results

        await self.mw.before_agent_start(state)

        assert hasattr(state, 'pending_subagent_tasks')
        assert hasattr(state, 'subagent_results')
        assert state.pending_subagent_tasks == []
        assert state.subagent_results == []

    @pytest.mark.asyncio
    async def test_after_tool_call_spawn_subagent(self):
        """spawn_subagent adds to pending tasks."""
        state = MagicMock(spec=ThreadState)
        state.pending_subagent_tasks = []
        state.subagent_results = []

        result = await self.mw.after_tool_call(
            state, "spawn_subagent",
            {"name": "worker", "task": "Do something", "subagent_type": "general"},
            "Started subagent subagent-abc123"
        )

        assert len(state.pending_subagent_tasks) == 1
        assert state.pending_subagent_tasks[0]["name"] == "worker"

    @pytest.mark.asyncio
    async def test_after_tool_call_get_subagent_results_replaces_placeholder(self):
        """get_subagent_results replaces placeholder with actual results."""
        state = MagicMock(spec=ThreadState)
        state.pending_subagent_tasks = []
        state.subagent_results = [
            {"subagent_id": "sub-1", "name": "worker", "output": "Task completed", "status": "completed"}
        ]

        result = await self.mw.after_tool_call(
            state, "get_subagent_results",
            {},
            "[SUBAGENT_RESULTS_PLACEHOLDER]"
        )

        assert "SUBAGENT_RESULTS_PLACEHOLDER" not in result
        assert "worker" in result
        assert "completed" in result

    @pytest.mark.asyncio
    async def test_after_tool_call_passthrough_non_subagent(self):
        """Non-subagent tools pass through unchanged."""
        state = MagicMock(spec=ThreadState)
        result = "bash output"
        output = await self.mw.after_tool_call(state, "bash", {}, result)
        assert output == result

    @pytest.mark.asyncio
    async def test_after_agent_end_skips_when_no_llm(self):
        """Skips subagent execution when LLM not set."""
        mw = SubagentMiddleware()  # no LLM
        state = MagicMock(spec=ThreadState)
        state.pending_subagent_tasks = [{"name": "task"}]
        state.subagent_results = []

        await mw.after_agent_end(state)
        # Should not raise, just skip

    @pytest.mark.asyncio
    async def test_after_agent_end_skips_when_no_pending(self):
        """Skips when no pending subagent tasks."""
        mock_llm = MagicMock()
        mw = SubagentMiddleware(llm=mock_llm)
        state = MagicMock(spec=ThreadState)
        state.pending_subagent_tasks = []
        state.subagent_results = []

        await mw.after_agent_end(state)
        # Should not raise, LLM not called

    def test_extract_subagent_id(self):
        """Extracts subagent ID from result string."""
        result = "Started subagent subagent-abc123def456"
        sub_id = self.mw._extract_subagent_id(result)
        assert sub_id == "subagent-abc123def456"

    def test_extract_subagent_id_not_found(self):
        """Returns generated ID when pattern not found."""
        result = "No subagent ID here"
        sub_id = self.mw._extract_subagent_id(result)
        assert sub_id.startswith("subagent-")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
