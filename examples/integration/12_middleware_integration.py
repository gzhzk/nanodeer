"""Example 12: Middleware Integration.

Demonstrates:
- UploadsMiddleware: process uploaded files
- CompressionMiddleware: compress long conversations
- MiddlewareChain: combine multiple middlewares
"""
import asyncio
from pathlib import Path
from langchain_core.messages import HumanMessage, AIMessage
from harness.agent.state import ThreadState
from harness.middlewares import MiddlewareChain, UploadsMiddleware, CompressionMiddleware
from unittest.mock import AsyncMock, MagicMock
import tempfile


def main():
    print("=" * 60)
    print("Example 12: Middleware Integration")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # UploadsMiddleware
        uploads_mw = UploadsMiddleware(base_path=Path(tmpdir))
        print("\n1. UploadsMiddleware:")
        print("-" * 40)

        state = ThreadState(
            thread_id="upload-test",
            uploaded_files=[
                {"name": "notes.txt", "content": "Important project notes", "mime_type": "text/plain"},
            ],
        )

        asyncio.run(uploads_mw.before_agent_start(state))
        print(f"   Files: {state.uploaded_files}")
        print(f"   Memory context: {state.memory_context[:50]}...")

        # CompressionMiddleware
        print("\n2. CompressionMiddleware:")
        print("-" * 40)

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "User discussed many topics."
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        compression_mw = CompressionMiddleware(
            llm=mock_llm,
            threshold=5,
            keep_recent=2,
        )

        # Long conversation
        messages = [
            HumanMessage(content="Message 1"),
            AIMessage(content="Response 1"),
            HumanMessage(content="Message 2"),
            AIMessage(content="Response 2"),
            HumanMessage(content="Message 3"),
            AIMessage(content="Response 3"),
        ]

        state = ThreadState(thread_id="compress-test", messages=messages)
        asyncio.run(compression_mw.before_agent_start(state))

        print(f"   Before: 6 messages")
        print(f"   After: {len(state.messages)} messages")
        print(f"   First msg: {state.messages[0].content[:30]}...")

        # MiddlewareChain
        print("\n3. MiddlewareChain:")
        print("-" * 40)

        chain = MiddlewareChain([
            UploadsMiddleware(base_path=Path(tmpdir)),
            CompressionMiddleware(llm=mock_llm, threshold=10),
        ])

        state = ThreadState(
            thread_id="chain-test",
            uploaded_files=[{"name": "doc.txt", "content": "Content", "mime_type": "text/plain"}],
            messages=[HumanMessage(content="Hello")],
        )

        asyncio.run(chain.before_agent_start(state))
        print(f"   Chain executed {len(chain.middlewares)} middlewares")
        print(f"   Memory context set: {'memory_context' in state.memory_context.lower() or 'doc.txt' in (state.memory_context or '')}")

    print("\n✅ Middlewares can be chained and work together")


if __name__ == "__main__":
    main()
