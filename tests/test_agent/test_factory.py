"""Tests for NanoDeerFactory — feature-gated middleware assembly."""

import pytest
from unittest.mock import MagicMock

from nanodeer.agent.factory import (
    NanoDeerFactory,
    RuntimeFeatures,
    create_nanodeer_agent,
)


class MockLLM:
    def __init__(self):
        self.call_count = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.call_count += 1
        resp = MagicMock()
        resp.content = "Done"
        resp.tool_calls = None
        return resp


class MockTool:
    def __init__(self, name="mock_tool"):
        self.name = name

    async def ainvoke(self, args, exec_id=None):
        return "mock result"


class TestRuntimeFeatures:
    def test_default_values(self):
        f = RuntimeFeatures()
        assert f.uploads is True
        assert f.compression is True
        assert f.sandbox is True
        assert f.clarification is True
        assert f.prompt_memory is True
        assert f.prompt_todos is True
        assert f.prompt_skills is True
        assert f.prompt_subagent is True
        assert f.context_window == 204800
        assert f.compression_ratio == 0.7
        assert f.compression_keep_recent == 5

    def test_custom_values(self):
        f = RuntimeFeatures(
            uploads=False,
            sandbox=False,
            context_window=100000,
        )
        assert f.uploads is False
        assert f.sandbox is False
        assert f.context_window == 100000


class TestNanoDeerFactory:
    def test_build_with_defaults(self):
        """Assembles executor with all default features."""
        factory = NanoDeerFactory(RuntimeFeatures())
        llm = MockLLM()
        tools = [MockTool()]

        executor, compression_mw = factory.build(llm, tools)

        assert executor is not None
        assert compression_mw is not None

    def test_uploads_false_excludes_file_middleware(self):
        """FileMiddleware is skipped when uploads=False."""
        factory = NanoDeerFactory(RuntimeFeatures(uploads=False))
        llm = MockLLM()
        tools = [MockTool()]

        executor, _ = factory.build(llm, tools)

        # Middleware chain has no FileMiddleware
        for hook_name in ["_before_llm", "_after_llm", "_before_tools", "_after_tools_all"]:
            hook = getattr(executor._chain, hook_name, [])
            names = [m.__class__.__name__ for m in hook]
            assert "FileMiddleware" not in names

    def test_sandbox_false_no_sandbox_provider(self):
        """Sandbox provider not created when sandbox=False."""
        factory = NanoDeerFactory(RuntimeFeatures(sandbox=False))
        llm = MockLLM()
        tools = [MockTool()]

        executor, _ = factory.build(llm, tools)

        # Should not crash; sandbox is disabled
        assert executor is not None

    def test_clarification_false_excludes_clarification_middleware(self):
        """ClarificationMiddleware is skipped when clarification=False."""
        factory = NanoDeerFactory(RuntimeFeatures(clarification=False))
        llm = MockLLM()
        tools = [MockTool()]

        executor, _ = factory.build(llm, tools)

        names = [m.__class__.__name__ for m in executor._chain._after_llm]
        assert "ClarificationMiddleware" not in names

    def test_compression_false_no_compression_middleware(self):
        """CompressionMiddleware is None when compression=False."""
        factory = NanoDeerFactory(RuntimeFeatures(compression=False))
        llm = MockLLM()
        tools = [MockTool()]

        _, compression_mw = factory.build(llm, tools)
        assert compression_mw is None

    def test_memory_store_passed_to_memory_middleware(self):
        """memory_store arg is passed to MemoryMiddleware."""
        factory = NanoDeerFactory(RuntimeFeatures())
        llm = MockLLM()
        tools = [MockTool()]
        mock_store = MagicMock()

        executor, _ = factory.build(llm, tools, memory_store=mock_store)

        # Find MemoryMiddleware in chain
        for m in executor._chain._before_llm:
            if m.__class__.__name__ == "MemoryMiddleware":
                assert m._memory_store is mock_store
                break

    def test_extra_middlewares_injected(self):
        """extra_middlewares dict injects custom middlewares."""
        factory = NanoDeerFactory(RuntimeFeatures())
        llm = MockLLM()
        tools = [MockTool()]

        class CustomMiddleware:
            async def before_llm(self, state, signals):
                pass

        executor, _ = factory.build(
            llm, tools,
            extra_middlewares={"before_llm": [CustomMiddleware()]},
        )

        names = [m.__class__.__name__ for m in executor._chain._before_llm]
        assert "CustomMiddleware" in names


class TestCreateNanoDeerAgent:
    def test_returns_executor_and_compression(self):
        """create_nanodeer_agent is a shortcut for factory.build()."""
        agent = create_nanodeer_agent(model=MockLLM(), tools=[MockTool()])
        executor, compression = agent
        assert executor is not None
        assert compression is not None

    def test_none_tools_uses_default(self):
        """tools=None falls back to default_tools()."""
        llm = MockLLM()
        agent = create_nanodeer_agent(model=llm, tools=None)
        executor, _ = agent
        # Should not crash; default tools are used
        assert executor is not None

    def test_none_features_uses_defaults(self):
        """features=None uses default RuntimeFeatures."""
        agent = create_nanodeer_agent(model=MockLLM(), tools=[MockTool()], features=None)
        executor, _ = agent
        assert executor is not None