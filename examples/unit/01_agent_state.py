"""Example 01: ThreadState and SandboxInfo - Agent state management.

Demonstrates:
- Creating ThreadState with messages
- ThreadState fields and defaults
- SandboxInfo structure
"""
from langchain_core.messages import HumanMessage
from harness.agent.state import ThreadState, SandboxInfo


def main():
    print("=" * 60)
    print("Example 01: ThreadState and SandboxInfo")
    print("=" * 60)

    # Create empty ThreadState
    state = ThreadState()
    print(f"\nEmpty state:")
    print(f"  messages: {state.messages}")
    print(f"  thread_id: {state.thread_id}")
    print(f"  sandbox: {state.sandbox}")
    print(f"  artifacts: {state.artifacts}")

    # Create with messages
    messages = [HumanMessage(content="Hello, who are you?")]
    state = ThreadState(messages=messages, thread_id="user-001")
    print(f"\nWith messages:")
    print(f"  messages: {len(state.messages)} message(s)")
    print(f"  thread_id: {state.thread_id}")

    # Create SandboxInfo
    sandbox = SandboxInfo(
        thread_id="user-001",
        container_id="abc123",
        status="ready",
        working_dir="/workspace/user-001"
    )
    print(f"\nSandboxInfo:")
    print(f"  thread_id: {sandbox.thread_id}")
    print(f"  container_id: {sandbox.container_id}")
    print(f"  status: {sandbox.status}")
    print(f"  working_dir: {sandbox.working_dir}")

    print("\n✅ ThreadState and SandboxInfo are the core state structures")
    print("   that flow through the LangGraph state machine.")


if __name__ == "__main__":
    main()
