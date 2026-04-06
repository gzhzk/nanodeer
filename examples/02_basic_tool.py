"""Example 02: Agent with All File Tools

Run with: python -m examples.02_basic_tool

This example demonstrates:
- All 5 file tools: read_file, write_file, ls, glob, grep
- How the agent decides which tool to call based on user input
- How tool results are fed back to the agent for final response

Tools available:
- read_file: Read file content
- write_file: Write content to a file (base64-encoded, safe)
- ls: List directory contents (like ls -la)
- glob: Find files by pattern (like find -name)
- grep: Search for text in files (like grep -r)
"""

import asyncio
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from harness.agent import make_lead_agent, ThreadState
from harness.config import get_config
from harness.tools.file import read_file, write_file, ls, glob, grep


async def main():
    print("=" * 60)
    print("NanoDeer All File Tools Demo")
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

    tools = [read_file, write_file, ls, glob, grep]
    agent = make_lead_agent(llm=llm, tools=tools, checkpointer_type=None)

    # Prepare a temp directory with some files for the agent to work with
    test_dir = "/tmp/nanodeer_example02"
    os.makedirs(f"{test_dir}/workspace", exist_ok=True)

    # Write a few test files
    files = {
        f"{test_dir}/workspace/hello.py": "def greet(name):\n    return f'Hello, {name}!'",
        f"{test_dir}/workspace/utils.py": "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b",
        f"{test_dir}/workspace/README.txt": "This is a sample project.",
    }
    for path, content in files.items():
        with open(path, "w") as f:
            f.write(content)

    print(f"\nTest files created in {test_dir}/workspace:")
    for name in files:
        print(f"  - {os.path.basename(name)}")

    # Ask agent to explore and search the files
    initial_state = ThreadState(
        messages=[HumanMessage(
            content=f"""Do the following in order:
            1. List the files in {test_dir}/workspace
            2. Read hello.py and tell me the greet function
            3. Search for "def add" in {test_dir}/workspace
            4. Find all .py files in {test_dir}/workspace"""
        )],
        thread_id="example-02",
    )

    print("\nRunning agent with tools (read_file, write_file, ls, glob, grep)...\n")
    result = await agent.ainvoke(initial_state)

    print("Conversation flow:")
    for msg in result["messages"]:
        print(f"\n[{type(msg).__name__}]")
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                print(f"  → Tool call: {tc['name']}({tc['args']})")
        content = msg.content
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'text':
                    print(f"  Content: {block.get('text', '')[:200]}...")
                elif isinstance(block, dict) and block.get('type') == 'thinking':
                    print(f"  Thinking: {block.get('thinking', '')[:50]}...")
        else:
            print(f"  Content: {str(content)[:200]}...")

    print("\n" + "=" * 60)
    print("✅ All file tools demo completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
