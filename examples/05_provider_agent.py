"""Example 05: Provider-based Agent with Tools

Run with: python -m examples.05_provider_agent

Demonstrates:
- Provider-based config (new pattern)
- Agent with file tools
- System prompt injection with thread_id
"""
import asyncio

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from harness.agent import AgentBuilder, ThreadState
from harness.config import get_config


async def main():
    """Run agent with provider-based config."""
    print("=" * 60)
    print("Example 05: Provider-based Agent")
    print("=" * 60)

    # New provider-based config
    config = get_config()
    model = config.agents.defaults.model
    provider_name = config.agents.defaults.provider

    print(f"Model: {model}")
    print(f"Provider: {provider_name}")

    # Get provider config
    p = config.get_provider_config(provider_name)
    if not p:
        print(f"❌ Provider '{provider_name}' not configured")
        return

    api_key = p.api_key
    api_base = p.api_base or None  # None means use default

    print(f"API Base: {api_base or '(default)'}")

    # Create LLM
    llm = ChatAnthropic(
        model=model,
        anthropic_api_key=api_key,
        base_url=api_base,
    )

    # Import tools
    from harness.tools.file import ReadFile, WriteFile

    # Create agent
    tools = [ReadFile, WriteFile]
    builder = AgentBuilder(llm=llm, tools=tools, checkpointer=None)
    agent = builder.build()

    # Create a test file
    test_file = "/tmp/nanodeer_example05.txt"
    with open(test_file, "w") as f:
        f.write("Hello from NanoDeer provider example!")

    # Create initial state
    initial_state = ThreadState(
        messages=[HumanMessage(
            content=f"Read the file at {test_file} and tell me what it says."
        )],
        thread_id="example-05",
    )

    print(f"\nRunning agent (thread_id={initial_state.thread_id})...")
    print("-" * 60)

    result = await agent.ainvoke(initial_state)

    print("\nResult:")
    print("-" * 60)
    for msg in result["messages"]:
        role = type(msg).__name__
        content = msg.content[:500] if len(msg.content) > 500 else msg.content
        print(f"[{role}]: {content}")
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                print(f"  → Tool: {tc['name']}({tc['args']})")

    print("\n✅ Provider example completed!")


if __name__ == "__main__":
    asyncio.run(main())