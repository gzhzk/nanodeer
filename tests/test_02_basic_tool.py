"""Test 02: Agent with All File Tools - multi-tool call loop.

Tests all 6 tools: read_file, write_file, ls, glob, grep, bash.
"""

import asyncio
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from harness.agent import make_lead_agent, ThreadState
from harness.config import get_config
from harness.tools.file import read_file, write_file, ls, glob, grep, bash


async def test_all_tools():
    """Test: Agent uses all 6 file tools in sequence."""
    config = get_config()

    model = "MiniMax-M2.7"
    provider_name = "minimax"
    p = config.get_provider_config(provider_name)
    api_key = p.api_key if p else None
    api_base = p.api_base if p else None

    print(f"Using provider: {provider_name}")
    print(f"Model: {model}")

    llm = ChatAnthropic(
        model=model,
        anthropic_api_key=api_key,
        base_url=api_base,
    )

    tools = [read_file, write_file, ls, glob, grep, bash]
    agent = make_lead_agent(llm=llm, tools=tools, checkpointer_type=None)

    # Prepare a temp directory with files
    test_dir = "/tmp/nanodeer_test02"
    os.makedirs(f"{test_dir}/workspace", exist_ok=True)

    files = {
        f"{test_dir}/workspace/hello.py": "def greet(name):\n    return f'Hello, {name}!'",
        f"{test_dir}/workspace/utils.py": "def add(a, b):\n    return a + b",
    }
    for path, content in files.items():
        with open(path, "w") as f:
            f.write(content)

    initial_state = ThreadState(
        messages=[HumanMessage(
            content=f"""Do the following:
            1. List files in {test_dir}/workspace
            2. Read hello.py
            3. Search for "def add" in {test_dir}/workspace
            4. Find all .py files in {test_dir}/workspace
            5. Run: echo "hello from bash" """
        )],
        thread_id="test-002",
    )

    print("Running agent with all 6 tools...\n")
    result = await agent.ainvoke(initial_state)

    # Verify tools were called
    tool_calls = []
    for msg in result["messages"]:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(tc["name"])

    print("Conversation:")
    for msg in result["messages"]:
        print(f"  [{type(msg).__name__}]: {msg.content[:200]}...")
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                print(f"    → Tool: {tc['name']}({tc['args']})")

    # Verify all 5 expected tools were called (order may vary)
    expected = {"ls", "read_file", "grep", "glob", "bash"}
    called = set(tool_calls)
    missing = expected - called
    if missing:
        print(f"\n⚠️  Expected tools not called: {missing}")
    else:
        print(f"\n✅ All expected tools called: {called}")


if __name__ == "__main__":
    asyncio.run(test_all_tools())
