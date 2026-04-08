"""Integration tests for AgentBuilder with mocked LLM."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage

from harness.agent import AgentBuilder, ThreadState
from harness.agent.prompt import build_lead_agent_prompt


class TestAgentBuilder:
    """Test AgentBuilder graph construction."""

    def test_builder_requires_llm(self):
        """Builder requires LLM parameter."""
        with pytest.raises(TypeError):
            AgentBuilder()

    def test_builder_with_empty_tools(self):
        """Builder accepts empty tools list."""
        mock_llm = MagicMock()
        builder = AgentBuilder(llm=mock_llm, tools=[])
        assert builder.llm is not None
        assert builder._raw_tools == []

    def test_builder_stores_tools(self):
        """Builder stores tools."""
        mock_llm = MagicMock()

        class FakeTool:
            name = "test_tool"

        builder = AgentBuilder(llm=mock_llm, tools=[FakeTool()])
        assert len(builder._raw_tools) == 1

    def test_build_returns_compiled_graph(self):
        """build() returns compiled StateGraph."""
        mock_llm = MagicMock()
        builder = AgentBuilder(llm=mock_llm, tools=[])

        graph = builder.build()
        assert graph is not None
        assert hasattr(graph, "invoke")

    def test_build_binds_tools_to_llm(self):
        """build() binds tools to LLM."""
        mock_llm = MagicMock()

        class FakeTool:
            name = "test_tool"

        builder = AgentBuilder(llm=mock_llm, tools=[FakeTool()])
        builder.build()

        # Verify bind_tools was called
        mock_llm.bind_tools.assert_called_once()


class TestAgentNode:
    """Test agent node logic."""

    def test_agent_node_uses_system_prompt(self):
        """Agent node builds system prompt correctly."""
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="Response"))

        builder = AgentBuilder(llm=mock_llm, tools=[])
        builder.build()

        state = ThreadState(
            messages=[HumanMessage(content="Hello")],
            thread_id="test-123",
        )

        # The _agent_node uses build_lead_agent_prompt
        from harness.agent.prompt import build_lead_agent_prompt
        prompt = build_lead_agent_prompt(
            tools=[],
            thread_id="test-123",
        )
        assert "NanoDeer" in prompt
        assert "test-123" in prompt


class TestToolExecutorNode:
    """Test tool executor node logic."""

    def test_tool_executor_handles_no_tool_calls(self):
        """Tool executor handles message without tool calls."""
        # If last message has no tool_calls, should return empty
        # This is tested via the _should_continue logic
        from harness.agent.builder import AgentBuilder

        builder = AgentBuilder(llm=MagicMock(), tools=[])
        builder.build()

        state = ThreadState(messages=[AIMessage(content="Just a response")])

        # should_continue should return "end"
        result = builder._should_continue(state)
        assert result == "end"


class TestShouldContinue:
    """Test conditional edge routing."""

    def test_end_when_no_tool_calls(self):
        """Routes to end when no tool calls."""
        from harness.agent.builder import AgentBuilder

        builder = AgentBuilder(llm=MagicMock(), tools=[])
        builder.build()

        state = ThreadState(messages=[AIMessage(content="Just a response")])
        assert builder._should_continue(state) == "end"

    def test_continue_when_has_tool_calls(self):
        """Routes to tools when has tool calls."""
        from harness.agent.builder import AgentBuilder
        from langchain_core.messages import AIMessage, FunctionMessage

        builder = AgentBuilder(llm=MagicMock(), tools=[])
        builder.build()

        # Message with tool_calls
        msg = AIMessage(content="", tool_calls=[{
            "name": "ReadFile",
            "args": {"file_path": "/tmp/test"},
            "id": "call_123",
        }])
        state = ThreadState(messages=[msg])
        assert builder._should_continue(state) == "continue"


class TestMiddlewareIntegration:
    """Test middleware integration with agent."""

    def test_invoke_with_hooks_calls_middleware(self):
        """ainvoke_with_hooks calls middleware hooks."""
        from harness.middlewares.base import Middleware

        mock_middleware = AsyncMock()
        mock_middleware.before_agent_start = AsyncMock()
        mock_middleware.after_agent_end = AsyncMock()

        mock_llm = MagicMock()

        builder = AgentBuilder(
            llm=mock_llm,
            tools=[],
            middleware_chain=mock_middleware,
        )
        builder.build()

        state = ThreadState(
            messages=[HumanMessage(content="Hello")],
            thread_id="test",
        )

        # Mock the compiled graph invoke
        with patch.object(builder, "_compiled") as mock_compiled:
            mock_compiled.ainvoke = AsyncMock(return_value={"messages": []})
            asyncio.run(builder.ainvoke_with_hooks(state))

        # Verify middleware hooks were called
        mock_middleware.before_agent_start.assert_called_once()
        mock_middleware.after_agent_end.assert_called_once()

    def test_invoke_without_middleware(self):
        """ainvoke_without_middleware works."""
        mock_llm = MagicMock()

        builder = AgentBuilder(llm=mock_llm, tools=[])
        builder.build()

        state = ThreadState(
            messages=[HumanMessage(content="Hello")],
            thread_id="test",
        )

        # Should not raise even without middleware
        with patch.object(builder, "_compiled") as mock_compiled:
            mock_compiled.ainvoke = AsyncMock(return_value={"messages": []})
            result = asyncio.run(builder.ainvoke_with_hooks(state))
            assert "messages" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
