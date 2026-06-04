"""Tests for NanoDeerFactory — feature-gated agent assembly."""

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
        assert f.sandbox is True
        assert f.compression is True
        assert f.prompt_memory is True
        assert f.prompt_plan is True
        assert f.prompt_skills is True
        assert f.prompt_subagent is True
        assert f.context_window == 204800
        assert f.compression_ratio == 0.7
        assert f.compression_keep_recent == 5

    def test_custom_values(self):
        f = RuntimeFeatures(
            sandbox=False,
            compression=False,
            context_window=100000,
        )
        assert f.sandbox is False
        assert f.compression is False
        assert f.context_window == 100000


class TestNanoDeerFactory:
    def test_build_returns_executor(self):
        """build() returns a ReActExecutor."""
        factory = NanoDeerFactory(RuntimeFeatures())
        llm = MockLLM()
        tools = [MockTool()]

        executor = factory.build(llm, tools)

        assert executor is not None
        assert executor.llm is llm
        assert len(executor._tools) == 1

    def test_sandbox_false_no_sandbox_provider(self):
        """Sandbox manager not created when sandbox=False."""
        factory = NanoDeerFactory(RuntimeFeatures(sandbox=False))
        llm = MockLLM()
        tools = [MockTool()]

        executor = factory.build(llm, tools)

        assert executor is not None
        assert executor._sandbox is None

    def test_subagent_provider_exists_when_sandbox_false(self):
        """Subagents still need a provider for worker lifecycle."""
        factory = NanoDeerFactory(RuntimeFeatures(sandbox=False))
        llm = MockLLM()
        tools = [MockTool()]

        factory.build(llm, tools)

        from nanodeer.subagent import get_executor
        from nanodeer.sandbox.local import LocalSandboxProvider

        assert isinstance(get_executor().sandbox_provider, LocalSandboxProvider)

    def test_compression_false_no_compression_middleware(self):
        """CompressionMiddleware is None when compression=False."""
        factory = NanoDeerFactory(RuntimeFeatures(compression=False))
        llm = MockLLM()
        tools = [MockTool()]

        compression_mw = factory.build_compression(llm)
        assert compression_mw is None

    def test_compression_true_builds_middleware(self):
        """CompressionMiddleware built when compression=True."""
        factory = NanoDeerFactory(RuntimeFeatures(compression=True))
        llm = MockLLM()

        compression_mw = factory.build_compression(llm)
        assert compression_mw is not None
        assert compression_mw.context_window == 204800

    def test_build_with_memory_store(self):
        """memory_store arg is passed through to ContextManager."""
        factory = NanoDeerFactory(RuntimeFeatures())
        llm = MockLLM()
        tools = [MockTool()]
        mock_store = MagicMock()

        executor = factory.build(llm, tools, memory_store=mock_store)

        assert executor._context._memory_store is mock_store

    def test_tool_map_is_built(self):
        """Tool map is populated from wrapped tools."""
        factory = NanoDeerFactory(RuntimeFeatures(sandbox=False))
        llm = MockLLM()
        tools = [MockTool("tool_a"), MockTool("tool_b")]

        executor = factory.build(llm, tools)

        assert "tool_a" in executor._tool_map
        assert "tool_b" in executor._tool_map


class TestCreateNanoDeerAgent:
    def test_returns_executor_and_compression(self):
        """create_nanodeer_agent returns (executor, compression_mw)."""
        agent = create_nanodeer_agent(model=MockLLM(), tools=[MockTool()])
        executor, compression = agent
        assert executor is not None
        assert compression is not None

    def test_none_tools_uses_default(self):
        """tools=None falls back to default_tools()."""
        llm = MockLLM()
        agent = create_nanodeer_agent(model=llm, tools=None)
        executor, _ = agent
        assert executor is not None

    def test_none_features_uses_defaults(self):
        """features=None uses default RuntimeFeatures."""
        agent = create_nanodeer_agent(model=MockLLM(), tools=[MockTool()], features=None)
        executor, _ = agent
        assert executor is not None
