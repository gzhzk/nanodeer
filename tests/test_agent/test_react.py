"""Tests for ReActExecutor — native async ReAct loop."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from nanodeer.agent.react import ReActExecutor
from nanodeer.agent.state import NextAction, ThreadState, TurnSignals
from nanodeer.agent.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from nanodeer.agent.prompt import PromptConfig


class MockLLM:
    """LLM that returns a simple response without tool calls."""

    def __init__(self, response_content="Done", tool_calls=None):
        self.response_content = response_content
        self._tool_calls = tool_calls
        self.call_count = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.call_count += 1
        resp = MagicMock()
        resp.content = self.response_content
        resp.tool_calls = self._tool_calls
        return resp


class MockTool:
    """Tool that returns a fixed result."""

    def __init__(self, name="mock_tool", result="mock result"):
        self.name = name
        self._result = result

    async def ainvoke(self, args, exec_id=None):
        return self._result


class MockChain:
    """Chain that does nothing by default."""

    def __init__(self):
        self._before_llm_calls = []
        self._after_llm_calls = []
        self._before_tools_calls = []
        self._after_tools_all_calls = []

    async def before_llm(self, state, signals):
        self._before_llm_calls.append((state, signals))

    async def after_llm(self, state, signals):
        self._after_llm_calls.append((state, signals))

    async def before_tools(self, state, signals, tool_name, tool_args):
        self._before_tools_calls.append((state, signals, tool_name, tool_args))

    async def after_tools_all(self, state, signals):
        self._after_tools_all_calls.append((state, signals))


class TestReActExecutorInit:
    def test_binds_tools_to_llm(self):
        """Tools are bound to LLM at init."""
        llm = MockLLM()
        tools = [MockTool("tool_a"), MockTool("tool_b")]
        chain = MockChain()
        executor = ReActExecutor(llm, tools, chain)

        # Should not raise; tools are bound
        assert executor.llm is llm
        assert executor._tools == tools

    def test_prompt_config_default(self):
        """Default PromptConfig has all flags True."""
        llm = MockLLM()
        executor = ReActExecutor(llm, [], MockChain())
        assert executor._prompt_config.memory is True
        assert executor._prompt_config.todos is True
        assert executor._prompt_config.skills is True
        assert executor._prompt_config.subagent is True


class TestReActLoop:
    @pytest.mark.asyncio
    async def test_ends_when_no_tool_calls(self):
        """Loop ends when LLM returns no tool calls."""
        llm = MockLLM(response_content="Final answer")
        tools = [MockTool()]
        chain = MockChain()
        executor = ReActExecutor(llm, tools, chain)

        state = ThreadState(thread_id="t1", messages=[HumanMessage(content="Hi")])
        final = await executor.run(state)

        assert final.next_action == NextAction.PROCESS
        assert len(final.messages) == 2  # HumanMessage + AIMessage

    @pytest.mark.asyncio
    async def test_executes_tool_calls(self):
        """Tool calls from LLM are executed and results appended."""
        tc = {"name": "mock_tool", "args": {"arg1": "value1"}, "id": "call-1"}

        llm = MockLLM(response_content="Thinking...", tool_calls=[tc])
        tools = [MockTool(name="mock_tool", result="tool result")]
        chain = MockChain()
        executor = ReActExecutor(llm, tools, chain)

        state = ThreadState(thread_id="t1", messages=[HumanMessage(content="Hi")])
        final = await executor.run(state)

        # State has HumanMessage + AIMessage + ToolMessage
        assert len(final.messages) == 3
        tool_msg = final.messages[-1]
        assert tool_msg.content == "tool result"

    @pytest.mark.asyncio
    async def test_next_action_end_from_before_llm(self):
        """Middleware can set next_action=END to stop loop."""
        chain = MockChain()
        original_before_llm = chain.before_llm

        async def early_end(state, signals):
            await original_before_llm(state, signals)
            state.next_action = NextAction.END

        chain.before_llm = early_end

        llm = MockLLM(response_content="Should not run")
        executor = ReActExecutor(llm, [], chain)

        state = ThreadState(thread_id="t1", messages=[HumanMessage(content="Hi")])
        final = await executor.run(state)

        # LLM should not be called
        assert llm.call_count == 0

    @pytest.mark.asyncio
    async def test_next_action_wait_from_after_llm(self):
        """Clarification sets next_action=WAIT and returns."""
        chain = MockChain()
        original_after_llm = chain.after_llm

        async def clarification_wait(state, signals):
            await original_after_llm(state, signals)
            state.next_action = NextAction.WAIT

        chain.after_llm = clarification_wait

        llm = MockLLM(response_content="Question?")
        executor = ReActExecutor(llm, [], chain)

        state = ThreadState(thread_id="t1", messages=[HumanMessage(content="Hi")])
        final = await executor.run(state)

        assert final.next_action == NextAction.WAIT
        assert llm.call_count == 1  # One call before WAIT

    @pytest.mark.asyncio
    async def test_before_tools_can_interrupt(self):
        """before_tools middleware can set next_action=END to stop loop."""
        chain = MockChain()
        original_before_tools = chain.before_tools

        async def block_tool(state, signals, tool_name, tool_args):
            await original_before_tools(state, signals, tool_name, tool_args)
            state.next_action = NextAction.END

        chain.before_tools = block_tool

        tc = {"name": "mock_tool", "args": {}, "id": "call-1"}

        llm = MockLLM(response_content="Thinking", tool_calls=[tc])
        tools = [MockTool()]
        executor = ReActExecutor(llm, tools, chain)

        state = ThreadState(thread_id="t1", messages=[HumanMessage(content="Hi")])
        final = await executor.run(state)

        # Tool should not be executed
        assert len(final.messages) == 2  # No ToolMessage added

    @pytest.mark.asyncio
    async def test_executor_uses_thread_id_for_exec_id(self):
        """Tool calls use state.thread_id as exec_id."""
        exec_ids_seen = []

        class TrackingTool:
            name = "mock"
            async def ainvoke(self, args, exec_id=None):
                exec_ids_seen.append(exec_id)
                return "done"

        chain = MockChain()

        tc = {"name": "mock", "args": {}, "id": "call-1"}

        llm = MockLLM(response_content="Thinking", tool_calls=[tc])
        executor = ReActExecutor(llm, [TrackingTool()], chain)

        state = ThreadState(thread_id="thread-abc", messages=[HumanMessage(content="Hi")])
        await executor.run(state)

        assert exec_ids_seen == ["thread-abc"]

    @pytest.mark.asyncio
    async def test_executor_falls_back_to_default_exec_id(self):
        """None thread_id uses 'default' as exec_id."""
        exec_ids_seen = []

        class TrackingTool:
            name = "mock"
            async def ainvoke(self, args, exec_id=None):
                exec_ids_seen.append(exec_id)
                return "done"

        chain = MockChain()

        tc = {"name": "mock", "args": {}, "id": "call-1"}

        llm = MockLLM(response_content="Thinking", tool_calls=[tc])
        executor = ReActExecutor(llm, [TrackingTool()], chain)

        state = ThreadState(thread_id=None, messages=[HumanMessage(content="Hi")])
        await executor.run(state)

        assert exec_ids_seen == ["default"]


class TestReActExecutorToolNotFound:
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error_message(self):
        """Tool not in tool map returns error ToolMessage."""
        chain = MockChain()

        tc = {"name": "nonexistent_tool", "args": {}, "id": "call-1"}

        llm = MockLLM(response_content="Calling tool", tool_calls=[tc])
        tools = [MockTool(name="some_other_tool")]  # not the one called
        executor = ReActExecutor(llm, tools, chain)

        state = ThreadState(thread_id="t1", messages=[HumanMessage(content="Hi")])
        final = await executor.run(state)

        tool_msg = final.messages[-1]
        assert "not found" in tool_msg.content