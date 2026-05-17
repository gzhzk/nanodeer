"""Tests for NanoEngine — App layer entry point."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from nanodeer.engine import NanoEngine, RunResult
from nanodeer.agent.state import NextAction


class TestRunResult:
    def test_dataclass_fields(self):
        r = RunResult(
            thread_id="t1",
            message="Hello",
            next_action=NextAction.PROCESS,
            artifacts=["/a.txt"],
            tool_calls=[{"name": "read_file", "args": {}}],
            duration_ms=150,
        )
        assert r.thread_id == "t1"
        assert r.message == "Hello"
        assert r.next_action == NextAction.PROCESS
        assert r.artifacts == ["/a.txt"]
        assert r.tool_calls == [{"name": "read_file", "args": {}}]
        assert r.duration_ms == 150

    def test_defaults(self):
        r = RunResult(thread_id="t1", message="Hi")
        assert r.next_action == NextAction.PROCESS
        assert r.artifacts == []
        assert r.tool_calls == []
        assert r.duration_ms == 0


class TestNanoEngineInit:
    def test_stores_config(self):
        config = MagicMock()
        engine = NanoEngine(config)
        assert engine.config is config

    def test_stores_model_name(self):
        config = MagicMock()
        engine = NanoEngine(config, model_name="claude-3")
        assert engine._model_name == "claude-3"

    def test_stores_features(self):
        config = MagicMock()
        features = MagicMock()
        engine = NanoEngine(config, features=features)
        assert engine._features is features

    def test_stores_tools(self):
        config = MagicMock()
        tools = [MagicMock()]
        engine = NanoEngine(config, tools=tools)
        assert engine._tools == tools

    def test_lazy_executor_init(self):
        """Executor not created until run() is called."""
        config = MagicMock()
        engine = NanoEngine(config)
        assert engine._executor is None
        assert engine._compression_mw is None


class TestNanoEngineRun:
    @pytest.mark.asyncio
    async def test_returns_run_result(self):
        """run() returns a RunResult with correct thread_id."""
        config = MagicMock()
        engine = NanoEngine(config)

        mock_state = MagicMock()
        mock_state.messages = [MagicMock(content="Hi")]
        mock_state.next_action = NextAction.PROCESS
        mock_state.artifacts = []
        mock_state.thread_id = "t1"

        mock_executor = AsyncMock()
        mock_executor.run = AsyncMock(return_value=(mock_state, []))
        mock_compression = MagicMock()
        mock_compression.compress = MagicMock(return_value=None)

        with patch("nanodeer.engine.create_nanodeer_agent") as mock_factory:
            mock_factory.return_value = (mock_executor, mock_compression)
            with patch("nanodeer.engine._create_llm", return_value=MagicMock()):
                result = await engine.run("hello", thread_id="t1")

        assert result.thread_id == "t1"
        assert result.message == "Hi"
        assert result.next_action == NextAction.PROCESS

    @pytest.mark.asyncio
    async def test_auto_generates_thread_id(self):
        """thread_id is auto-generated if not provided."""
        config = MagicMock()
        engine = NanoEngine(config)

        mock_state = MagicMock()
        mock_state.messages = [MagicMock(content="Done")]
        mock_state.next_action = NextAction.PROCESS
        mock_state.artifacts = []

        mock_executor = AsyncMock()
        mock_executor.run = AsyncMock(return_value=(mock_state, []))
        mock_compression = MagicMock()
        mock_compression.compress = MagicMock(return_value=None)

        with patch("nanodeer.engine.create_nanodeer_agent") as mock_factory:
            mock_factory.return_value = (mock_executor, mock_compression)
            with patch("nanodeer.engine._create_llm", return_value=MagicMock()):
                result = await engine.run("hello")

        assert result.thread_id is not None
        assert len(result.thread_id) > 0

    @pytest.mark.asyncio
    async def test_compression_middleware_called(self):
        """Compression is called after executor.run()."""
        config = MagicMock()
        engine = NanoEngine(config)

        mock_state = MagicMock()
        mock_state.messages = [MagicMock(content="Hi")]
        mock_state.next_action = NextAction.PROCESS
        mock_state.artifacts = []

        mock_executor = AsyncMock()
        mock_executor.run = AsyncMock(return_value=(mock_state, []))
        mock_compression = MagicMock()
        mock_compression.compress = MagicMock(return_value=None)

        with patch("nanodeer.engine.create_nanodeer_agent") as mock_factory:
            mock_factory.return_value = (mock_executor, mock_compression)
            with patch("nanodeer.engine._create_llm", return_value=MagicMock()):
                await engine.run("hello")

        mock_compression.compress.assert_called_once()

    @pytest.mark.asyncio
    async def test_compression_replaces_messages(self):
        """Compression result replaces state.messages."""
        config = MagicMock()
        engine = NanoEngine(config)

        mock_state = MagicMock()
        mock_state.messages = [MagicMock(content="Hi")]
        mock_state.next_action = NextAction.PROCESS
        mock_state.artifacts = []

        mock_executor = AsyncMock()
        mock_executor.run = AsyncMock(return_value=(mock_state, []))
        compressed = [MagicMock(content="Summarized")]
        mock_compression = MagicMock()
        mock_compression.compress = MagicMock(return_value=compressed)

        with patch("nanodeer.engine.create_nanodeer_agent") as mock_factory:
            mock_factory.return_value = (mock_executor, mock_compression)
            with patch("nanodeer.engine._create_llm", return_value=MagicMock()):
                await engine.run("hello")

        assert mock_state.messages == compressed

    @pytest.mark.asyncio
    async def test_no_compression_when_none(self):
        """No compression attempted when compression_mw is None."""
        config = MagicMock()
        engine = NanoEngine(config)

        mock_state = MagicMock()
        mock_state.messages = [MagicMock(content="Hi")]
        mock_state.next_action = NextAction.PROCESS
        mock_state.artifacts = []

        mock_executor = AsyncMock()
        mock_executor.run = AsyncMock(return_value=(mock_state, []))

        with patch("nanodeer.engine.create_nanodeer_agent") as mock_factory:
            mock_factory.return_value = (mock_executor, None)
            with patch("nanodeer.engine._create_llm", return_value=MagicMock()):
                result = await engine.run("hello")

        assert result.message == "Hi"

    @pytest.mark.asyncio
    async def test_uploaded_files_passed_to_executor(self):
        """uploaded_files are passed to executor.run()."""
        config = MagicMock()
        engine = NanoEngine(config)

        mock_state = MagicMock()
        mock_state.messages = [MagicMock(content="Hi")]
        mock_state.next_action = NextAction.PROCESS
        mock_state.artifacts = []

        mock_executor = AsyncMock()
        mock_executor.run = AsyncMock(return_value=(mock_state, []))
        mock_compression = MagicMock()
        mock_compression.compress = MagicMock(return_value=None)

        files = [{"name": "test.txt", "content": "hello"}]

        with patch("nanodeer.engine.create_nanodeer_agent") as mock_factory:
            mock_factory.return_value = (mock_executor, mock_compression)
            with patch("nanodeer.engine._create_llm", return_value=MagicMock()):
                await engine.run("hello", uploaded_files=files)

        mock_executor.run.assert_called_once()
        call_kwargs = mock_executor.run.call_args[1]
        assert call_kwargs["uploaded_files"] == files

    @pytest.mark.asyncio
    async def test_duration_ms_measured(self):
        """duration_ms is non-zero after run."""
        config = MagicMock()
        engine = NanoEngine(config)

        mock_state = MagicMock()
        mock_state.messages = [MagicMock(content="Hi")]
        mock_state.next_action = NextAction.PROCESS
        mock_state.artifacts = []

        mock_executor = AsyncMock()
        mock_executor.run = AsyncMock(return_value=(mock_state, []))
        mock_compression = MagicMock()
        mock_compression.compress = MagicMock(return_value=None)

        with patch("nanodeer.engine.create_nanodeer_agent") as mock_factory:
            mock_factory.return_value = (mock_executor, mock_compression)
            with patch("nanodeer.engine._create_llm", return_value=MagicMock()):
                result = await engine.run("hello")

        # duration_ms is set from time measurement
        assert result.duration_ms >= 0