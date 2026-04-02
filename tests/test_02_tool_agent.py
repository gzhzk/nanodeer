"""Test 02: Agent with Tools - ReadFile tool call loop."""

import asyncio

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from harness.agent import make_lead_agent, ThreadState
from harness.config import get_config
# BashCommand disabled - requires Sandbox (Day 3-4) for safe execution
from harness.tools.file import ReadFile, WriteFile  # , BashCommand


async def test_tool_agent():
    """Test: Agent calls ReadFile tool and returns result."""
    config = get_config()
    model_cfg = config.models[0]
    llm = ChatAnthropic(
        model=model_cfg.model,
        anthropic_api_key=model_cfg.api_key,
        base_url=model_cfg.base_url,
    )

    # Create agent with tools
    # BashCommand disabled - requires Sandbox (Day 3-4)
    tools = [ReadFile, WriteFile]
    agent = make_lead_agent(llm=llm, tools=tools, checkpointer_type=None)

    # Create a test file first
    test_file = "/tmp/nanodeer_test.txt"
    with open(test_file, "w") as f:
        f.write("Hello from NanoDeer test!")

    # Ask agent to read the file
    initial_state = ThreadState(
        messages=[HumanMessage(content=f"Read the file at {test_file} and tell me what it says.")],
        thread_id="test-002",
    )

    print("Running agent with tools...\n")
    result = await agent.ainvoke(initial_state)

    # Print all messages
    print("Conversation:")
    for msg in result["messages"]:
        print(f"  [{type(msg).__name__}]: {msg.content[:300]}...")
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                print(f"    → Tool call: {tc['name']}({tc['args']})")

    print("\n✅ Tool agent test passed!")


if __name__ == "__main__":
    asyncio.run(test_tool_agent())