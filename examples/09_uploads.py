"""Example 09: UploadsMiddleware - handling user-uploaded files.

Run with: python -m examples.09_uploads

This example demonstrates:
- UploadsMiddleware processes files before agent starts
- Text files are read and injected into memory_context
- Files are stored in /mnt/user-data/uploads/
- Agent can access uploaded files via read_file tool
"""

import asyncio
import tempfile
from pathlib import Path

from harness.agent.state import ThreadState
from harness.middlewares import UploadsMiddleware


async def demo_uploads_middleware():
    """Demo: UploadsMiddleware processes files and injects into context."""
    print("\n=== UploadsMiddleware Demo ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        middleware = UploadsMiddleware(base_path=Path(tmpdir))

        # Simulate uploaded files (in real usage, these come from HTTP upload)
        state = ThreadState(
            thread_id="upload-demo",
            uploaded_files=[
                {
                    "name": "notes.txt",
                    "content": "My name is Kai.\nI prefer Python over other languages.\nI work on AI projects.",
                    "mime_type": "text/plain",
                },
                {
                    "name": "config.json",
                    "content": '{"model": "MiniMax-M2.7", "temperature": 0.7}',
                    "mime_type": "application/json",
                },
            ],
        )

        print("Before middleware:")
        print(f"  uploaded_files: {len(state.uploaded_files)}")
        print(f"  memory_context: {state.memory_context}")

        await middleware.before_agent_start(state)

        print("\nAfter middleware:")
        print(f"  Files written to: {tmpdir}/upload-demo/user-data/uploads/")
        for f in (Path(tmpdir) / "upload-demo" / "user-data" / "uploads").iterdir():
            print(f"    - {f.name} ({f.stat().st_size} bytes)")

        print(f"\n  memory_context (injected):")
        print(f"  {state.memory_context[:300]}...")


async def demo_binary_file():
    """Demo: Binary files are noted but content not read."""
    print("\n=== Binary File Demo ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        middleware = UploadsMiddleware(base_path=Path(tmpdir))

        state = ThreadState(
            thread_id="binary-demo",
            uploaded_files=[
                {
                    "name": "image.png",
                    "content": None,  # Binary - no text content
                    "mime_type": "image/png",
                },
            ],
        )

        await middleware.before_agent_start(state)

        print("Binary file handling:")
        print(f"  memory_context:\n{state.memory_context}")


async def main():
    print("=" * 60)
    print("NanoDeer UploadsMiddleware Demo")
    print("=" * 60)

    await demo_uploads_middleware()
    await demo_binary_file()

    print("\n" + "=" * 60)
    print("✅ UploadsMiddleware demos passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
