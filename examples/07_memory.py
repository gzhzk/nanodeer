"""Example 07: Memory system - file-based memory storage and injection."""

import asyncio
import tempfile
from pathlib import Path

from harness.memory import MemoryStore, MemoryEntry
from harness.middlewares import MemoryMiddleware, MiddlewareChain
from harness.agent import ThreadState
from langchain_core.messages import HumanMessage


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


async def demo_memory_middleware():
    """Demo: MemoryMiddleware integration with agent state."""
    print("\n=== MemoryMiddleware Demo ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(root=Path(tmpdir))

        # Pre-populate memory
        store.save_user_memory(
            user_id="test-user",
            content="The user is a senior Python developer who prefers direct answers.",
            name="developer_profile",
            description="senior Python developer",
        )

        # Create middleware
        memory_mw = MemoryMiddleware(store, project_slug="test-project")

        # Create a state
        state = ThreadState(
            messages=[HumanMessage(content="Hello, who am I?")],
            thread_id="test-user",
        )

        # Before agent starts - middleware loads memory
        print(f"Before middleware: memory_context = {state.memory_context!r}")
        await memory_mw.before_agent_start(state)
        print(f"After middleware:  memory_context = {state.memory_context!r}")

        # Verify memory was loaded into state
        assert state.memory_context is not None
        assert "senior Python developer" in state.memory_context
        print("\n✅ MemoryMiddleware correctly injected memory into state")


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


async def main():
    print("=" * 60)
    print("NanoDeer Memory System Demo")
    print("=" * 60)

    await demo_frontmatter()
    await demo_memory_store()
    await demo_memory_middleware()

    print("\n" + "=" * 60)
    print("✅ All memory demos passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())