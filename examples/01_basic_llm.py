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
    """Run a simple agent that can respond to messages."""
    config = get_config()

    # Get first model from config
    model_cfg = config.models[0]
    llm = ChatAnthropic(
        model=model_cfg.model,
        anthropic_api_key=model_cfg.api_key,
        base_url=model_cfg.base_url,
    )

    # Create the agent graph
    # Note: tools=[] means NO tools - this is just a basic LLM call
    agent = make_lead_agent(llm=llm, tools=[])

    # Create initial state
    initial_state = ThreadState(
        messages=[HumanMessage(content="Hello, who are you?")],
        thread_id="test-001",
    )

    # Run the agent
    print("Running agent...\n")
    result = await agent.ainvoke(initial_state)

    # Print the response
    print("Agent response:")
    for message in result["messages"]:
        print(f"  [{type(message).__name__}]: {message.content[:200]}...")


if __name__ == "__main__":
    asyncio.run(main())
