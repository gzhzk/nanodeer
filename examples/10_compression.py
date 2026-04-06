"""Example 10: CompressionMiddleware - context summarization.

Run with: python -m examples.10_compression

This example demonstrates:
- CompressionMiddleware triggers when messages exceed threshold
- Old messages are summarized by LLM
- Summary replaces old messages, keeping recent ones intact
"""

import asyncio
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from harness.agent.state import ThreadState
from harness.middlewares import CompressionMiddleware


async def demo_compression_triggered():
    """Demo: Compression triggers when messages exceed threshold."""
    print("\n=== Compression Triggered Demo ===")

    # Mock LLM that returns a summary
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "User discussed AI projects, preferred Python, asked about memory systems."
    mock_llm.ainvoke = asyncio.coroutine(
        lambda x: mock_response
    )

    # Create middleware with low threshold for testing
    middleware = CompressionMiddleware(
        llm=mock_llm,
        threshold=5,
        keep_recent=2,
    )

    # Create state with 8 messages (exceeds threshold of 5)
    messages = [
        HumanMessage(content="I want to work on an AI agent project"),
        AIMessage(content="Great! AI agents are exciting. What domain?"),
        HumanMessage(content="I prefer Python, maybe with LangGraph"),
        AIMessage(content="LangGraph is a good choice. It handles state well."),
        HumanMessage(content="Yes, and I want memory and planning too"),
        AIMessage(content="So you want memory for context and planning for tasks?"),
        HumanMessage(content="Exactly, and sandbox isolation for safety"),
        AIMessage(content="Sandbox isolation is important for security."),
    ]

    state = ThreadState(
        thread_id="compression-demo",
        messages=messages,
    )

    print(f"Before: {len(state.messages)} messages")

    await middleware.before_agent_start(state)

    print(f"After:  {len(state.messages)} messages")
    print(f"\nFirst message (summary):")
    print(f"  {state.messages[0].content[:100]}...")
    print(f"\nLast 2 messages (preserved):")
    for msg in state.messages[-2:]:
        print(f"  {type(msg).__name__}: {msg.content[:50]}...")


async def demo_no_compression():
    """Demo: No compression when messages below threshold."""
    print("\n=== No Compression Demo ===")

    mock_llm = MagicMock()
    middleware = CompressionMiddleware(
        llm=mock_llm,
        threshold=10,  # High threshold
        keep_recent=2,
    )

    messages = [
        HumanMessage(content="Hello"),
        AIMessage(content="Hi there!"),
        HumanMessage(content="How are you?"),
    ]

    state = ThreadState(
        thread_id="no-compression-demo",
        messages=messages,
    )

    original_len = len(state.messages)
    await middleware.before_agent_start(state)

    print(f"Messages: {original_len} (below threshold of 10)")
    print(f"LLM called: {mock_llm.ainvoke.called}")
    print(f"Messages unchanged: {len(state.messages) == original_len}")


async def main():
    print("=" * 60)
    print("NanoDeer CompressionMiddleware Demo")
    print("=" * 60)

    await demo_compression_triggered()
    await demo_no_compression()

    print("\n" + "=" * 60)
    print("✅ CompressionMiddleware demos passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())