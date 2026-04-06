"""Example 03: Middleware Chain + Security Validation

Run with: python -m examples.03_middleware_security

This example demonstrates:
- ThreadDataMiddleware creates thread directory structure
- SecurityMiddleware validates paths and commands
- Middleware hook execution order (before_* forward, after_* reverse)

Prerequisites: None (no real Docker/API required)
"""

import asyncio

from harness.agent.state import ThreadState
from harness.middlewares import (
    MiddlewareChain,
    ThreadDataMiddleware,
    SecurityMiddleware,
    SecurityError,
)


async def demo_middleware_chain():
    """Demo: MiddlewareChain hook execution order."""
    print("\n=== MiddlewareChain Demo ===")

    thread_data = ThreadDataMiddleware()
    security = SecurityMiddleware()
    chain = MiddlewareChain([thread_data, security])

    state = ThreadState(thread_id="example-03")

    print("  before_agent_start (forward: ThreadData → Security)")
    await chain.before_agent_start(state)
    print(f"  ✓ sandbox.status = {state.sandbox.status}")

    print("\n  after_agent_end (reverse: Security → ThreadData)")
    await chain.after_agent_end({})
    print("  ✓ cleanup completed")


async def demo_security_validation():
    """Demo: SecurityMiddleware path and command validation."""
    print("\n=== SecurityMiddleware Demo ===")

    chain = MiddlewareChain([SecurityMiddleware()])
    state = ThreadState(thread_id="example-03")

    # Valid path
    try:
        await chain.before_tool_call(
            state, "read_file", {"file_path": "/mnt/user-data/workspace/code.py"}
        )
        print("  ✓ read_file('/mnt/user-data/workspace/code.py') - valid")
    except SecurityError as e:
        print(f"  ✗ {e}")

    # Path traversal
    try:
        await chain.before_tool_call(
            state, "write_file", {"file_path": "/mnt/user-data/../etc/passwd"}
        )
        print("  ✗ Should have blocked path traversal")
    except SecurityError as e:
        print("  ✓ Blocked path traversal")


async def main():
    print("=" * 60)
    print("NanoDeer Middleware Chain Demo")
    print("=" * 60)

    await demo_middleware_chain()
    await demo_security_validation()

    print("\n" + "=" * 60)
    print("✅ All middleware demos passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
