"""Unit tests for ThreadState and agent state management."""
import pytest
from langchain_core.messages import HumanMessage, AIMessage

from nanodeer.agent.state import ThreadState, SandboxInfo


class TestThreadState:
    """Test ThreadState data structure."""

    def test_create_empty_state(self):
        """Empty ThreadState has correct defaults."""
        state = ThreadState()
        assert state.messages == []
        assert state.thread_id is None
        assert state.sandbox is not None
        assert state.artifacts == []
        assert state.todos == []
        assert state.memory_context is None
        assert state.subagent_results == []

    def test_create_with_thread_id(self):
        """ThreadState with thread_id."""
        state = ThreadState(thread_id="thread-abc")
        assert state.thread_id == "thread-abc"

    def test_create_with_messages(self):
        """ThreadState with initial messages."""
        msgs = [HumanMessage(content="hello")]
        state = ThreadState(messages=msgs)
        assert len(state.messages) == 1
        assert state.messages[0].content == "hello"

    def test_sandbox_info_defaults(self):
        """SandboxInfo has correct initial status."""
        info = SandboxInfo(thread_id="test")
        assert info.thread_id == "test"
        assert info.container_id is None
        assert info.status == "acquiring"
        assert info.working_dir is None

    def test_sandbox_info_ready(self):
        """SandboxInfo after container acquired."""
        info = SandboxInfo(
            thread_id="test",
            container_id="abc123",
            status="ready",
            working_dir="/workspace/test"
        )
        assert info.container_id == "abc123"
        assert info.status == "ready"
        assert info.working_dir == "/workspace/test"

    def test_todos_default_empty(self):
        """todos defaults to empty list."""
        state = ThreadState()
        assert state.todos == []

    def test_subagent_results_default_empty(self):
        """subagent_results defaults to empty list."""
        state = ThreadState()
        assert state.subagent_results == []

    def test_memory_context_default_none(self):
        """memory_context defaults to None."""
        state = ThreadState()
        assert state.memory_context is None


class TestSandboxInfo:
    """Test SandboxInfo model."""

    def test_status_transitions(self):
        """SandboxInfo status progression."""
        info = SandboxInfo(thread_id="t1", status="acquiring")
        assert info.status == "acquiring"

        info.status = "ready"
        assert info.status == "ready"

        info.status = "released"
        assert info.status == "released"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
