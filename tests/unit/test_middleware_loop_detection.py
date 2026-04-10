"""Unit tests for LoopDetectionMiddleware."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from langchain_core.messages import AIMessage, HumanMessage

from nanodeer.agent.middlewares.loop_detection import LoopDetectionMiddleware
from nanodeer.agent.state import ThreadState


class TestLoopDetectionMiddleware:
    """Test LoopDetectionMiddleware loop detection."""

    def setup_method(self):
        self.mw = LoopDetectionMiddleware(
            warn_threshold=3,
            hard_limit=5,
            window_size=20,
        )

    def test_initialization(self):
        """Middleware initializes with correct defaults."""
        assert self.mw.warn_threshold == 3
        assert self.mw.hard_limit == 5
        assert self.mw.window_size == 20
        assert self.mw.max_threads == 100

    def test_custom_init(self):
        """Custom threshold values."""
        mw = LoopDetectionMiddleware(warn_threshold=2, hard_limit=4, max_threads=50)
        assert mw.warn_threshold == 2
        assert mw.hard_limit == 4
        assert mw.max_threads == 50

    def test_hash_tool_calls_idempotent(self):
        """Same calls in different order produce same hash."""
        calls_a = [
            {"name": "bash", "args": {"command": "ls"}},
            {"name": "read_file", "args": {"path": "/tmp"}},
        ]
        calls_b = [
            {"name": "read_file", "args": {"path": "/tmp"}},
            {"name": "bash", "args": {"command": "ls"}},
        ]
        hash_a = self.mw._hash_tool_calls(calls_a)
        hash_b = self.mw._hash_tool_calls(calls_b)
        assert hash_a == hash_b

    def test_hash_tool_calls_different_args(self):
        """Different args produce different hash."""
        calls_a = [{"name": "bash", "args": {"command": "ls -la"}}]
        calls_b = [{"name": "bash", "args": {"command": "ls -lh"}}]
        hash_a = self.mw._hash_tool_calls(calls_a)
        hash_b = self.mw._hash_tool_calls(calls_b)
        assert hash_a != hash_b

    def test_history_new_tool_call(self):
        """New tool call adds to history."""
        thread_id = "test-thread"
        history = self.mw._get_history(thread_id)
        assert thread_id in self.mw._history
        assert len(history) == 0

    def test_lru_eviction(self):
        """LRU eviction when exceeding max_threads."""
        # Create middleware with small max_threads
        mw = LoopDetectionMiddleware(max_threads=2)
        mw._get_history("thread-1")
        mw._get_history("thread-2")
        mw._get_history("thread-3")  # Should evict thread-1
        assert "thread-1" not in mw._history
        assert "thread-2" in mw._history
        assert "thread-3" in mw._history

    def test_get_lock_creates_new_lock(self):
        """First access creates lock for thread."""
        import asyncio
        thread_id = "lock-test"
        lock = self.mw._get_lock(thread_id)
        assert isinstance(lock, asyncio.Lock)
        # Same thread gets same lock
        lock2 = self.mw._get_lock(thread_id)
        assert lock is lock2

    @pytest.mark.asyncio
    async def test_before_tool_call_first_call(self):
        """First tool call is recorded without warning."""
        state = MagicMock(spec=ThreadState)
        state.thread_id = "loop-test"
        state.messages = []

        await self.mw.before_tool_call(state, "bash", {"command": "ls"})
        history = self.mw._get_history("loop-test")
        assert len(history) == 1
        assert history[0][1] == 1  # count = 1

    @pytest.mark.asyncio
    async def test_before_tool_call_repeat_increments_count(self):
        """Repeated calls increment count in history."""
        state = MagicMock(spec=ThreadState)
        state.thread_id = "loop-test"
        state.messages = []

        # Call 3 times with same tool+args
        for _ in range(3):
            await self.mw.before_tool_call(state, "bash", {"command": "ls"})

        history = self.mw._get_history("loop-test")
        assert len(history) == 1
        assert history[0][1] == 3  # count = 3

    @pytest.mark.asyncio
    async def test_different_tools_different_history(self):
        """Different tools add separate history entries."""
        state = MagicMock(spec=ThreadState)
        state.thread_id = "loop-test"
        state.messages = []

        await self.mw.before_tool_call(state, "bash", {"command": "ls"})
        await self.mw.before_tool_call(state, "read_file", {"path": "/tmp"})

        history = self.mw._get_history("loop-test")
        assert len(history) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
