"""Tests for NanoEngine — App layer entry point."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from nanodeer.engine import NanoEngine, RunResult, RuntimeFeatures, _OPENAI_COMPATIBLE
from nanodeer.agent.messages import HumanMessage
from nanodeer.agent.state import NextAction, ThreadState, WaitState


class TestRunResult:
    def test_dataclass_fields(self):
        r = RunResult(
            thread_id="t1",
            message="Hello",
            next_action=NextAction.FINISH,
            tool_calls=[{"name": "read_file", "args": {}}],
            duration_ms=150,
        )
        assert r.thread_id == "t1"
        assert r.message == "Hello"
        assert r.next_action == NextAction.FINISH
        assert r.tool_calls == [{"name": "read_file", "args": {}}]
        assert r.duration_ms == 150

    def test_defaults(self):
        r = RunResult(thread_id="t1", message="Hi")
        assert r.next_action == NextAction.FINISH
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

    def test_stores_context_transform_extension(self):
        config = MagicMock()
        transform = AsyncMock()

        engine = NanoEngine(config, context_transform=transform)

        assert engine._context_transform is transform

    def test_lazy_loop_init(self):
        """Loop dependencies are not bound until first use."""
        config = MagicMock()
        engine = NanoEngine(config)
        assert engine._loop is None


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
    """Injects the callable Loop boundary directly."""

    def test_get_agent_returns_one_owner_per_thread(self):
        config = MagicMock()
        engine = NanoEngine(config)
        engine._loop = MagicMock()

        first = engine.get_agent("thread-1")
        second = engine.get_agent("thread-1")
        other = engine.get_agent("thread-2")

        assert first is second
        assert first is not other

        assert engine.forget_agent("thread-1") is True
        assert engine.get_cached_agent("thread-1") is None

    @pytest.mark.asyncio
    async def test_returns_run_result(self):
        """run() returns a RunResult with correct thread_id."""
        config = MagicMock()
        engine = NanoEngine(config)

        async def complete(
            state, uploaded_files=None, *, stream_llm=False, sink=None
        ):
            state.messages.append(MagicMock(content="Hi"))
            state.next_action = NextAction.FINISH
            return state, []

        engine._loop = AsyncMock(side_effect=complete)

        result = await engine.run("hello", thread_id="t1")

        assert result.thread_id == "t1"
        assert result.message == "Hi"
        assert result.next_action == NextAction.FINISH

    @pytest.mark.asyncio
    async def test_auto_generates_thread_id(self):
        """thread_id is auto-generated if not provided."""
        config = MagicMock()
        engine = NanoEngine(config)

        async def complete(
            state, uploaded_files=None, *, stream_llm=False, sink=None
        ):
            state.messages.append(MagicMock(content="Done"))
            state.next_action = NextAction.FINISH
            return state, []

        engine._loop = AsyncMock(side_effect=complete)

        result = await engine.run("hello")

        assert result.thread_id is not None
        assert len(result.thread_id) > 0

    @pytest.mark.asyncio
    async def test_uploaded_files_passed_to_loop(self):
        """uploaded_files cross the Agent-to-Loop boundary."""
        config = MagicMock()
        engine = NanoEngine(config)

        async def complete(
            state, uploaded_files=None, *, stream_llm=False, sink=None
        ):
            state.messages.append(MagicMock(content="Hi"))
            state.next_action = NextAction.FINISH
            return state, []

        loop = AsyncMock(side_effect=complete)
        engine._loop = loop

        files = [{"name": "test.txt", "content": "hello"}]
        await engine.run("hello", uploaded_files=files)

        loop.assert_called_once()
        assert loop.call_args.args[1] == files

    @pytest.mark.asyncio
    async def test_duration_ms_measured(self):
        """duration_ms is non-zero after run."""
        config = MagicMock()
        engine = NanoEngine(config)

        async def complete(
            state, uploaded_files=None, *, stream_llm=False, sink=None
        ):
            state.messages.append(MagicMock(content="Hi"))
            state.next_action = NextAction.FINISH
            return state, []

        engine._loop = AsyncMock(side_effect=complete)

        result = await engine.run("hello")

        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_user_reply_consumes_persisted_wait_before_resume(self):
        config = MagicMock()
        engine = NanoEngine(config, generate_titles=False)
        saved = ThreadState(
            thread_id="t-wait",
            messages=[HumanMessage(content="Original request")],
            next_action=NextAction.WAIT,
            finish_reason="wait",
            wait=WaitState(
                question="Which account?",
                required_input="account id",
                tool_call_id="call-wait",
            ),
        )
        engine._checkpointer = AsyncMock()
        engine._checkpointer.load = AsyncMock(return_value=saved)

        async def complete(
            state, uploaded_files=None, *, stream_llm=False, sink=None
        ):
            assert state.next_action is None
            assert state.wait is None
            assert state.finish_reason == "running"
            assert state.messages[-1].content == "account-42"
            state.next_action = NextAction.FINISH
            state.finish_reason = "completed"
            return state, []

        engine._loop = AsyncMock(side_effect=complete)

        result = await engine.run("account-42", thread_id="t-wait")

        assert result.next_action == NextAction.FINISH
