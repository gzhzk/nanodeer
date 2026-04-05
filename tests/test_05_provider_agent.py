"""Test 05: Full System Integration Test

Tests the complete system including:
- Provider-based config loading
- Agent with tools and system prompt injection
- Middleware chain lifecycle
- thread_id in system prompt
"""
import asyncio
import tempfile
from pathlib import Path

import pytest

from harness.agent import AgentBuilder, ThreadState
from harness.agent.prompt import build_lead_agent_prompt
from harness.config import get_config
from harness.middlewares import MiddlewareChain, SecurityMiddleware, ThreadDataMiddleware
from harness.middlewares.sandbox import SandboxMiddleware
from harness.sandbox.docker import DockerSandboxProvider
from harness.tools.file import ReadFile, WriteFile
from langchain_core.messages import HumanMessage


class TestProviderConfig:
    """Test provider-based configuration."""

    def test_load_config(self):
        """Config loads successfully."""
        config = get_config()
        assert config.agents.defaults.model == "MiniMax-M2.7"
        assert config.agents.defaults.provider == "minimax"

    def test_get_provider_config(self):
        """Get minimax provider config."""
        config = get_config()
        p = config.get_provider_config("minimax")
        assert p is not None
        assert p.api_key is not None
        assert "minimaxi" in (p.api_base or "")

    def test_get_nonexistent_provider(self):
        """Nonexistent provider returns None."""
        config = get_config()
        p = config.get_provider_config("nonexistent")
        assert p is None


class TestSystemPrompt:
    """Test system prompt generation."""

    def test_thread_id_injected(self):
        """thread_id is properly injected into prompt."""
        prompt = build_lead_agent_prompt(
            tools=["ReadFile", "WriteFile"],
            thread_id="test-thread-123",
        )
        assert "test-thread-123" in prompt
        assert "/workspace/test-thread-123" in prompt

    def test_thread_id_defaults_to_unset(self):
        """thread_id defaults to UNSET when not provided."""
        prompt = build_lead_agent_prompt(tools=[])
        assert "UNSET" in prompt

    def test_tools_section_generated(self):
        """Tools section is generated from tool names."""
        prompt = build_lead_agent_prompt(
            tools=["ReadFile", "WriteFile", "BashCommand"],
        )
        assert "ReadFile" in prompt
        assert "WriteFile" in prompt
        assert "BashCommand" in prompt


class TestMiddlewareChain:
    """Test middleware chain lifecycle."""

    def test_chain_creation(self):
        """MiddlewareChain creates successfully."""
        chain = MiddlewareChain([
            ThreadDataMiddleware(),
            SecurityMiddleware(),
        ])
        assert len(chain.middlewares) == 2


@pytest.mark.asyncio
class TestAgentWithProvider:
    """Test agent with provider-based config."""

    async def test_agent_basic(self):
        """Agent responds to simple message."""
        config = get_config()
        model = config.agents.defaults.model
        provider_name = config.agents.defaults.provider
        p = config.get_provider_config(provider_name)

        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            model=model,
            anthropic_api_key=p.api_key,
            base_url=p.api_base,
        )

        tools = [ReadFile, WriteFile]
        builder = AgentBuilder(llm=llm, tools=tools, checkpointer=None)
        agent = builder.build()

        # Create temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test content 123")
            temp_path = f.name

        try:
            initial_state = ThreadState(
                messages=[HumanMessage(content=f"Read {temp_path} and tell me what it says.")],
                thread_id="test-agent-basic",
            )

            result = await agent.ainvoke(initial_state)

            # Should have response
            assert len(result["messages"]) >= 2  # at least user + assistant
            last_msg = result["messages"][-1]
            assert last_msg.content  # has content
            print(f"\nAgent response: {last_msg.content[:200]}")

        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])