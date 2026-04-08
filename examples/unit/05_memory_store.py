"""Example 05: MemoryStore - File-based memory storage.

Demonstrates:
- Creating MemoryStore
- Saving user memory
- Saving project memory
- Loading combined memory
"""
import tempfile
from pathlib import Path
from harness.memory import MemoryStore


def main():
    print("=" * 60)
    print("Example 05: MemoryStore")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(root=Path(tmpdir))

        # Save user memory
        store.save_user_memory(
            user_id="kai",
            content="I prefer concise responses.",
            name="preference_concise",
            description="User likes brief answers",
        )
        print("\n1. Saved user memory for 'kai'")

        # Save project memory
        store.save_project_memory(
            user_id="kai",
            project_slug="nanodeer",
            content="NanoDeer is built with LangGraph.",
            name="tech_stack",
            description="Technology used",
        )
        print("2. Saved project memory for 'kai/nanodeer'")

        # Load combined memory
        memory = store.load("kai", "nanodeer")
        print("\n3. Loaded combined memory:")
        print("-" * 40)
        print(memory)

        # Load user memory only
        user_memory = store.load_user_memory("kai")
        print(f"\n4. User memory only ({len(user_memory)} chars)")

        # Check existence
        print(f"\n5. Memory exists:")
        print(f"  kai: {store.exists('kai')}")
        print(f"  kai/nanodeer: {store.exists('kai', 'nanodeer')}")
        print(f"  nonexistent: {store.exists('nonexistent')}")

        print("\n✅ MemoryStore persists data in frontmatter .md files")
        print("   Location: ~/.nanodeer/memory/{user_id}/")


if __name__ == "__main__":
    main()
