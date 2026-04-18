"""Tests for ThreadDataMiddleware."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from nanodeer.agent.middlewares.thread_data import ThreadDataMiddleware
from nanodeer.agent.state import ThreadState, TurnSignals


@pytest.fixture
def middleware():
    return ThreadDataMiddleware()


@pytest.fixture
def state():
    return ThreadState(thread_id="test-thread-123")


@pytest.fixture
def signals():
    return TurnSignals()


class TestThreadDataMiddleware:
    async def test_no_thread_id_skips(self, middleware, signals):
        """No thread_id → no-op."""
        state = ThreadState(thread_id=None)
        with patch("nanodeer.agent.middlewares.thread_data.get_config") as mock_cfg:
            mock_cfg.return_value.thread.storage_path = Path("/tmp/test")
            await middleware.before_llm(state, signals)
        # Should not raise

    async def test_creates_directory_structure(self, middleware, state, signals, tmp_path):
        """Creates workspace/uploads/outputs directories."""
        with patch("nanodeer.agent.middlewares.thread_data.get_config") as mock_cfg:
            mock_cfg.return_value.thread.storage_path = tmp_path
            await middleware.before_llm(state, signals)

        root = tmp_path / "test-thread-123" / "user-data"
        assert (root / "workspace").exists()
        assert (root / "uploads").exists()
        assert (root / "outputs").exists()

    async def test_idempotent_creation(self, middleware, state, signals, tmp_path):
        """Calling twice does not raise (exist_ok=True)."""
        with patch("nanodeer.agent.middlewares.thread_data.get_config") as mock_cfg:
            mock_cfg.return_value.thread.storage_path = tmp_path
            await middleware.before_llm(state, signals)
            await middleware.before_llm(state, signals)  # Should not raise
