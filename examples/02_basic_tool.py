"""Example 02: Agent with Tools

Run with: python -m examples.02_basic_tool

This example demonstrates:
- How to bind tools to an agent
- How the agent decides to call a tool based on user input
- How tool results are fed back to the agent for final response

Tools available:
- ReadFile: Read content from a file
- WriteFile: Write content to a file
- BashCommand: Execute a bash command (disabled - requires Sandbox, Day 3-4)
"""

import asyncio

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from harness.agent import make_lead_agent, ThreadState
from harness.config import get_config
# BashCommand disabled - requires Sandbox (Day 3-4) for safe execution
from harness.tools.file import ReadFile, WriteFile  # , BashCommand


async def main():
    """Run an agent with file and bash tools."""
    config = get_config()
    model = config.agents.defaults.model
    provider_name = config.agents.defaults.provider
    p = config.get_provider_config(provider_name)
    llm = ChatAnthropic(
        model=model,
        anthropic_api_key=p.api_key,
        base_url=p.api_base,
    )

    # Create agent with tools bound
    # BashCommand disabled - requires Sandbox (Day 3-4)
    tools = [ReadFile, WriteFile]
    # checkpointer_type=None disables persistence for simple examples
    agent = make_lead_agent(llm=llm, tools=tools, checkpointer_type=None)

    # Create a test file for the agent to read
    test_file = "/tmp/nanodeer_example02.txt"
    with open(test_file, "w") as f:
        f.write("Hello from NanoDeer Example 02!")

    # Ask agent to read the file
    initial_state = ThreadState(
        messages=[HumanMessage(content=f"Read the file at {test_file} and tell me what it says.")],
        thread_id="example-02",
    )

    print("Running agent with tools...\n")
    result = await agent.ainvoke(initial_state)

    # Print the conversation flow
    print("Conversation flow:")
    for msg in result["messages"]:
        print(f"\n[{type(msg).__name__}]")
        # Show tool calls if present
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                print(f"  → Tool call: {tc['name']}({tc['args']})")
        # Show content (truncated)
        content = msg.content
        if isinstance(content, list):
            # Handle MiniMax thinking format
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'text':
                    print(f"  Content: {block.get('text', '')[:100]}...")
                elif isinstance(block, dict) and block.get('type') == 'thinking':
                    print(f"  Thinking: {block.get('thinking', '')[:50]}...")
        else:
            print(f"  Content: {str(content)[:100]}...")


if __name__ == "__main__":
    asyncio.run(main())
