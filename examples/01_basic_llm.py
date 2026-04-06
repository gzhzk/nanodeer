"""Example 01: Basic LLM (No Tools)

Run with: python -m examples.01_basic_llm

This example demonstrates:
- How to create a Lead Agent with no tools
- How messages flow through the agent
- The simplest form of agent interaction (LLM only, no tool calling)

Note: This is NOT a full "agent" yet - it's just an LLM that responds.
      A true agent needs tools to interact with the world.
"""

import asyncio

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from harness.agent import make_lead_agent, ThreadState
from harness.config import get_config


async def main():
    print("=" * 60)
    print("NanoDeer Basic LLM Demo")
    print("=" * 60)

    config = get_config()
    model = config.agents.defaults.model
    provider_name = config.agents.defaults.provider
    p = config.get_provider_config(provider_name)
    llm = ChatAnthropic(
        model=model,
        anthropic_api_key=p.api_key,
        base_url=p.api_base,
    )

    agent = make_lead_agent(llm=llm, tools=[], checkpointer_type=None)

    initial_state = ThreadState(
        messages=[HumanMessage(content="Hello, who are you?")],
        thread_id="test-001",
    )

    print("\nRunning agent...\n")
    result = await agent.ainvoke(initial_state)

    print("Agent response:")
    for message in result["messages"]:
        print(f"  [{type(message).__name__}]: {message.content[:200]}...")

    print("\n" + "=" * 60)
    print("✅ Basic LLM demo completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
