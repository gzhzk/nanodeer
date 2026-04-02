"""Test 01: Minimal Agent + LLM conversation."""

import asyncio

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from harness.agent import make_lead_agent, ThreadState
from harness.config import get_config


async def test_basic_agent():
    """Test: Create agent and run a simple conversation."""
    config = get_config()

    # Get first model from config
    model_cfg = config.models[0]
    llm = ChatAnthropic(
        model=model_cfg.model,
        anthropic_api_key=model_cfg.api_key,
        base_url=model_cfg.base_url,
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
