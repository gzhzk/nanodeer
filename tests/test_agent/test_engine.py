"""Tests for NanoEngine — App layer entry point."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from nanodeer.engine import NanoEngine, RunResult, RuntimeFeatures, _OPENAI_COMPATIBLE
from nanodeer.agent.state import NextAction


class TestRunResult:
    def test_dataclass_fields(self):
        r = RunResult(
            thread_id="t1",
            message="Hello",
            next_action=NextAction.PROCESS,
            tool_calls=[{"name": "read_file", "args": {}}],
            duration_ms=150,
        )
        assert r.thread_id == "t1"
        assert r.message == "Hello"
        assert r.next_action == NextAction.PROCESS
        assert r.tool_calls == [{"name": "read_file", "args": {}}]
        assert r.duration_ms == 150

    def test_defaults(self):
        r = RunResult(thread_id="t1", message="Hi")
        assert r.next_action == NextAction.PROCESS
        assert r.tool_calls == []
        assert r.duration_ms == 0
        assert r.metrics == {}

    def test_extract_metrics_from_trace_events(self):
        events = [
            {"event": "turn_start"},
            {
                "event": "llm_end",
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            },
            {"event": "tool_call", "name": "read_file"},
            {"event": "tool_result", "name": "read_file", "success": True},
            {"event": "turn_start"},
            {"event": "llm_retry"},
            {
                "event": "llm_end",
                "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
            },
            {"event": "tool_result", "name": "bash", "success": False},
        ]

        metrics = NanoEngine._extract_metrics(events, duration_ms=123)

        assert metrics == {
            "duration_ms": 123,
            "num_turns": 2,
            "num_llm_calls": 2,
            "num_tool_calls": 1,
            "num_tool_errors": 1,
            "llm_retry_count": 1,
            "input_tokens": 17,
            "output_tokens": 8,
            "total_tokens": 25,
        }


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
        features = RuntimeFeatures()
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


class TestProviderRouting:
    def test_openai_compatible_provider_set_covers_config_examples(self):
        """Providers documented as OpenAI-compatible should route to ChatOpenAI."""
        expected = {
            "openai",
            "openrouter",
            "deepseek",
            "moonshot",
            "zhipu",
            "dashscope",
            "siliconflow",
            "gemini",
            "groq",
            "ollama",
        }
        assert expected <= _OPENAI_COMPATIBLE

    def test_minimax_stays_anthropic_compatible(self):
        """MiniMax config uses an Anthropic-compatible endpoint."""
        assert "minimax" not in _OPENAI_COMPATIBLE


class TestNanoEngineRun:
    """Injects mock executor directly (no factory mocking needed after v0.2 merge)."""

    @pytest.mark.asyncio
    async def test_returns_run_result(self):
        """run() returns a RunResult with correct thread_id."""
        config = MagicMock()
        engine = NanoEngine(config)

        mock_state = MagicMock()
        mock_state.messages = [MagicMock(content="Hi")]
        mock_state.next_action = NextAction.PROCESS
        mock_state.thread_id = "t1"

        mock_executor = AsyncMock()
        mock_executor._checkpointer = None
        mock_executor.run = AsyncMock(return_value=(mock_state, []))
        engine._executor = mock_executor

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

        mock_executor = AsyncMock()
        mock_executor._checkpointer = None
        mock_executor.run = AsyncMock(return_value=(mock_state, []))
        engine._executor = mock_executor

        result = await engine.run("hello")

        assert result.thread_id is not None
        assert len(result.thread_id) > 0

    @pytest.mark.asyncio
    async def test_uploaded_files_passed_to_executor(self):
        """uploaded_files are passed to executor.run()."""
        config = MagicMock()
        engine = NanoEngine(config)

        mock_state = MagicMock()
        mock_state.messages = [MagicMock(content="Hi")]
        mock_state.next_action = NextAction.PROCESS

        mock_executor = AsyncMock()
        mock_executor._checkpointer = None
        mock_executor.run = AsyncMock(return_value=(mock_state, []))
        engine._executor = mock_executor

        files = [{"name": "test.txt", "content": "hello"}]
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

        mock_executor = AsyncMock()
        mock_executor._checkpointer = None
        mock_executor.run = AsyncMock(return_value=(mock_state, []))
        engine._executor = mock_executor

        result = await engine.run("hello")

        assert result.duration_ms >= 0
