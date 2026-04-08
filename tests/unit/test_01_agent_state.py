"""Unit tests for ThreadState and agent state management."""
import pytest
from langchain_core.messages import HumanMessage, AIMessage

from harness.agent.state import ThreadState, SandboxInfo


class TestThreadState:
    """Test ThreadState data structure."""

    def test_create_empty_state(self):
        """Empty ThreadState has defaults."""
        state = ThreadState()
        assert state.messages == []
        assert state.thread_id is None
        assert state.sandbox is not None
        assert state.artifacts == []

    def test_create_with_messages(self):
        """ThreadState with messages."""
        messages = [HumanMessage(content="Hello")]
        state = ThreadState(messages=messages)
        assert len(state.messages) == 1
        assert state.messages[0].content == "Hello"

    def test_create_with_thread_id(self):
        """ThreadState with thread_id."""
        state = ThreadState(thread_id="test-123")
        assert state.thread_id == "test-123"

    def test_sandbox_info_defaults(self):
        """SandboxInfo has correct defaults."""
        info = SandboxInfo(thread_id="test")
        assert info.thread_id == "test"
        assert info.container_id is None
        assert info.status == "acquiring"

    def test_add_messages(self):
        """Messages can be added to state."""
        from langgraph.graph.message import add_messages

        state = ThreadState(messages=[HumanMessage(content="Hello")])
        new_messages = [AIMessage(content="Hi there")]
        state.messages = add_messages(state.messages, new_messages)
        assert len(state.messages) == 2

    def test_memory_context_default(self):
        """memory_context defaults to None."""
        state = ThreadState()
        assert state.memory_context is None

    def test_todos_default(self):
        """todos defaults to empty list."""
        state = ThreadState()
        assert state.todos == []

    def test_uploaded_files_default(self):
        """uploaded_files defaults to empty list."""
        state = ThreadState()
        assert state.uploaded_files == []


class TestSandboxInfo:
    """Test SandboxInfo model."""

    def test_create_with_values(self):
        """SandboxInfo with all values."""
        info = SandboxInfo(
            thread_id="user-123",
            container_id="abc456",
            status="ready",
            working_dir="/workspace/user-123"
        )
        assert info.thread_id == "user-123"
        assert info.container_id == "abc456"
        assert info.status == "ready"
        assert info.working_dir == "/workspace/user-123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
