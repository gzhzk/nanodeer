"""Example 04: MiddlewareChain - Hook execution order.

Demonstrates:
- MiddlewareChain creation
- before_* hooks execute in forward order
- after_* hooks execute in reverse order
- Why reverse cleanup matters
"""
import asyncio
from harness.agent.state import ThreadState
from harness.middlewares.base import MiddlewareChain, Middleware


class LogMiddleware(Middleware):
    """Middleware that logs when its hooks are called."""

    def __init__(self, name: str):
        self.name = name

    async def before_agent_start(self, state):
        print(f"  [before_agent_start] {self.name}")

    async def after_agent_end(self, state):
        print(f"  [after_agent_end] {self.name}")

    async def before_tool_call(self, state, tool_name, tool_args):
        print(f"  [before_tool_call] {self.name} → {tool_name}")

    async def after_tool_call(self, state, tool_name, tool_args, result):
        print(f"  [after_tool_call] {self.name} → {tool_name}")


def main():
    print("=" * 60)
    print("Example 04: MiddlewareChain Execution Order")
    print("=" * 60)

    # Create chain with 3 middlewares
    chain = MiddlewareChain([
        LogMiddleware("ThreadData"),
        LogMiddleware("Security"),
        LogMiddleware("Sandbox"),
    ])

    state = ThreadState(thread_id="test-001")

    print("\n1. before_agent_start (forward order):")
    print("-" * 40)
    asyncio.run(chain.before_agent_start(state))

    print("\n2. Tool call hooks:")
    print("-" * 40)
    asyncio.run(chain.before_tool_call(state, "ReadFile", {"file_path": "/tmp/test"}))
    asyncio.run(chain.after_tool_call(state, "ReadFile", {"file_path": "/tmp/test"}, "content..."))

    print("\n3. after_agent_end (reverse order):")
    print("-" * 40)
    asyncio.run(chain.after_agent_end(state))

    print("\n" + "=" * 60)
    print("Why Reverse Cleanup?")
    print("=" * 60)
    print("""
Like洗碗:
  - 先吃饭的人先放下筷子 (before: ThreadData → Security → Sandbox)
  - 最后吃完的人最后收桌子 (after: Sandbox → Security → ThreadData)

This ensures resources are released in correct order:
  1. Sandbox releases container last (still using it)
  2. Security cleans up after sandbox is done
  3. ThreadData cleans up at the very end
""")


if __name__ == "__main__":
    main()
