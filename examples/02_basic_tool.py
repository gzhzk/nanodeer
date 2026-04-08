"""Example 02: Agent with All 15 Tools

Run with: python -m examples.02_basic_tool

This example demonstrates all 15 tools across 6 categories:

File tools:
  - read_file: Read file content
  - write_file: Write content to file (base64-encoded, safe)
  - ls: List directory contents
  - glob: Find files by pattern
  - grep: Search text in files

Shell tool:
  - bash: Execute bash commands in sandbox

Web tools:
  - fetch_url: HTTP GET a URL and extract clean text
  - web_search: Search the web via DuckDuckGo

Python tool:
  - exec_python: Execute Python code in sandbox

Image tool:
  - read_image: Read image file and return base64 for vision LLM

Skill tool:
  - invoke_skill: Call a named skill to get its workflow prompt

Memory tool:
  - save_memory: Save information to the memory system

Plan tools:
  - write_todo: Add a todo item
  - list_todos: List all todo items
  - complete_todo: Mark a todo as completed
"""

import asyncio
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from harness.agent import make_lead_agent, ThreadState
from harness.config import get_config
from harness.tools import (
    read_file, write_file, ls, glob, grep, bash,
    fetch_url, web_search, read_image, exec_python,
    invoke_skill, save_memory,
    write_todo, list_todos, complete_todo,
)


def demo_all_tools():
    """Demonstrate all 15 tools with simple unit-style checks."""
    print("\n" + "=" * 60)
    print("Tool Inventory Check")
    print("=" * 60)

    tools = [
        read_file, write_file, ls, glob, grep, bash,
        fetch_url, web_search, read_image, exec_python,
        invoke_skill, save_memory,
        write_todo, list_todos, complete_todo,
    ]

    print(f"\nTotal: {len(tools)} tools")
    for t in tools:
        print(f"  ✅ {t.name}")

    # Show invoke_skill can load a skill
    print("\n--- invoke_skill check ---")
    result = invoke_skill.invoke({"skill_name": "web_scraper"})
    if "Skill 'web_scraper' not found" in result:
        print("  ⚠️  web_scraper skill not loaded (skills/ may not be in path)")
    else:
        print("  ✅ web_scraper skill loaded")
        print(f"  Prompt starts with: {result.split(chr(10))[0]}")


async def main():
    print("=" * 60)
    print("NanoDeer All 15 Tools Demo")
    print("=" * 60)

    # First show all tools are importable and named correctly
    demo_all_tools()

    # Then run a simple agent that uses file tools
    config = get_config()
    model = config.agents.defaults.model
    provider_name = config.agents.defaults.provider
    p = config.get_provider_config(provider_name)
    llm = ChatAnthropic(
        model=model,
        anthropic_api_key=p.api_key,
        base_url=p.api_base,
    )

    # Use file tools only for the live demo (simpler, no network needed)
    file_tools = [read_file, write_file, ls, glob, grep, bash]
    agent = make_lead_agent(llm=llm, tools=file_tools, checkpointer_type=None)

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
            4. Find all .py files in {test_dir}/workspace
            5. Run: echo "hello from bash" """
        )],
        thread_id="example-02",
    )

    print("\nRunning agent with file tools...")
    print("(Web/Python/Skill tools require network + actual LLM setup)\n")

    result = await agent.ainvoke(initial_state)

    print("\nConversation flow:")
    for msg in result["messages"]:
        print(f"\n[{type(msg).__name__}]")
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                print(f"  → Tool call: {tc['name']}({tc['args']})")
        content = msg.content
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    print(f"  Content: {block.get('text', '')[:200]}...")
                elif isinstance(block, dict) and block.get("type") == "thinking":
                    print(f"  Thinking: {block.get('thinking', '')[:50]}...")
        else:
            print(f"  Content: {str(content)[:200]}...")

    print("\n" + "=" * 60)
    print("✅ All 15 tools demo completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
