"""Test 01: Minimal Agent + LLM conversation."""

import asyncio

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from harness.agent import make_lead_agent, ThreadState
from harness.config import get_config


async def test_basic_agent():
    """Test: Create agent and run a simple conversation."""
    config = get_config()

    # Use minimax provider
    model = "MiniMax-M2.7"
    provider_name = "minimax"
    p = config.get_provider_config(provider_name)
    api_key = p.api_key if p else None
    api_base = p.api_base if p else None

    print(f"Using provider: {provider_name}")
    print(f"Model: {model}")
    print(f"API Base: {api_base}")

    llm = ChatAnthropic(
        model=model,
        anthropic_api_key=api_key,
        base_url=api_base,
    )

    # Create agent graph (no tools yet)
    agent = make_lead_agent(llm=llm, tools=[], checkpointer_type=None)

    # Create initial state
    initial_state = ThreadState(
        messages=[HumanMessage(content="Hello, who are you?")],
        thread_id="test-001",
    )

    # Run agent
    print("Running agent...\n")
    result = await agent.ainvoke(initial_state)

    # Print response
    print("Agent response:")
    last_message = result["messages"][-1]
    print(f"  [{type(last_message).__name__}]: {last_message.content[:200]}")
    print("\n✅ Test passed!")


if __name__ == "__main__":
    asyncio.run(test_basic_agent())
