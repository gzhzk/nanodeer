"""Example 07: Memory System v2 - file storage, auto-extraction, and SaveMemory tool.

Run with: python -m examples.07_memory

This example demonstrates:
- MemoryStore file operations (save/load)
- MemoryMiddleware before_agent_start (read injection)
- MemoryMiddleware after_tool_call (SaveMemory interception)
- MemoryMiddleware after_agent_end (auto-extraction)
- SaveMemory tool usage
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from harness.memory import MemoryStore, MemoryEntry, MemoryExtractor, ExtractedMemory
from harness.middlewares import MemoryMiddleware, MiddlewareChain
from harness.tools import SaveMemory
from harness.agent import ThreadState
from langchain_core.messages import HumanMessage, AIMessage


async def demo_frontmatter():
    """Demo: MemoryEntry frontmatter format."""
    print("\n=== Frontmatter Format Demo ===")

    entry = MemoryEntry(
        name="example_entry",
        description="This is an example memory entry",
        memory_type="user",
        content="This is the actual memory content.\nIt can span multiple lines.",
    )

    frontmatter = entry.to_frontmatter()
    print("Serialized frontmatter:")
    print(frontmatter)

    restored = MemoryEntry.from_frontmatter(frontmatter)
    print(f"\nRestored: name={restored.name}, type={restored.memory_type}")
    print(f"Content: {restored.content}")


async def demo_memory_store():
    """Demo: MemoryStore file operations."""
    print("\n=== MemoryStore Demo ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(root=Path(tmpdir))

        # Save user memory
        store.save_user_memory(
            user_id="kai",
            content="Prefers concise responses without lengthy summaries.",
            name="user_preference_terse",
            description="user likes terse output",
        )
        print("Saved user memory for 'kai'")

        # Save project memory
        store.save_project_memory(
            user_id="kai",
            project_slug="nanodeer",
            content="This project is a lightweight AI Agent harness. Tech stack: Python + LangGraph.",
            name="nanodeer_project",
            description="NanoDeer project context",
        )
        print("Saved project memory for 'kai/nanodeer'")

        # Load combined memory
        memory_context = store.load("kai", "nanodeer")
        print(f"\nLoaded memory context:\n{memory_context}")


async def demo_memory_middleware_v1():
    """Demo: MemoryMiddleware v1 - before_agent_start loads memory."""
    print("\n=== MemoryMiddleware v1 Demo ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(root=Path(tmpdir))

        # Pre-populate memory
        store.save_user_memory(
            user_id="test-user",
            content="The user is a senior Python developer who prefers direct answers.",
            name="developer_profile",
            description="senior Python developer",
        )

        # Create middleware (v1 mode - no extractor)
        memory_mw = MemoryMiddleware(store, project_slug="test-project")

        # Create a state
        state = ThreadState(
            messages=[HumanMessage(content="Hello, who am I?")],
            thread_id="test-user",
        )

        # Before agent starts - middleware loads memory
        print(f"Before middleware: has memory_context = {hasattr(state, 'memory_context')}")
        await memory_mw.before_agent_start(state)
        print(f"After middleware:  memory_context exists = {state.memory_context is not None}")

        # Verify memory was loaded into state
        assert state.memory_context is not None
        assert "senior Python developer" in state.memory_context
        print("✅ MemoryMiddleware correctly injected memory into state")


async def demo_save_memory_tool():
    """Demo: SaveMemory tool interception via after_tool_call."""
    print("\n=== SaveMemory Tool Demo (v2) ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(root=Path(tmpdir))

        # Create middleware
        memory_mw = MemoryMiddleware(store, project_slug="test-project")

        # Simulate SaveMemory tool call
        tool_args = {
            "content": "User prefers Python over other languages",
            "category": "user",
        }

        # after_tool_call intercepts SaveMemory and saves
        await memory_mw.after_tool_call(
            state={"thread_id": "test-user"},
            tool_name="SaveMemory",
            tool_args=tool_args,
            result="Memory saved",
        )

        # Verify memory was saved
        user_memory = store.load_user_memory("default")
        assert "Python" in user_memory
        print("✅ SaveMemory tool correctly saved memory via after_tool_call")


async def demo_auto_extraction():
    """Demo: after_agent_end auto-extraction via LLM."""
    print("\n=== Auto-Extraction Demo (v2) ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(root=Path(tmpdir))

        # Create mock LLM that returns structured memory
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '''[
            {
                "name": "User prefers Python",
                "description": "User likes Python over other languages",
                "category": "user",
                "content": "Always use Python for new projects",
                "keywords": ["python", "preference"]
            }
        ]'''
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        # Create extractor
        extractor = MemoryExtractor(mock_llm)

        # Create middleware with auto_extract enabled
        memory_mw = MemoryMiddleware(
            store,
            project_slug="test-project",
            extractor=extractor,
            auto_extract=True,
        )

        # Simulate agent result
        result = {
            "messages": [
                HumanMessage(content="I want to build a web app"),
                AIMessage(content="I'll help you build a web app using Python"),
            ],
        }

        # after_agent_end triggers extraction and saving
        await memory_mw.after_agent_end(result)

        # Verify memory was extracted and saved
        user_memory = store.load_user_memory("default")
        assert "Python" in user_memory
        print("✅ Auto-extraction correctly saved memory after agent ends")


async def main():
    print("=" * 60)
    print("NanoDeer Memory System v2 Demo")
    print("=" * 60)

    await demo_frontmatter()
    await demo_memory_store()
    await demo_memory_middleware_v1()
    await demo_save_memory_tool()
    await demo_auto_extraction()

    print("\n" + "=" * 60)
    print("✅ All memory demos passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())