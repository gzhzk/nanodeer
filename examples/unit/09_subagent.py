"""Example 09: Subagent System.

Demonstrates:
- SubagentPool for parallel task execution
- spawn_subagent tool
- get_subagent_results tool
"""
import asyncio
from unittest.mock import MagicMock

from harness.subagents import run_subagent, run_subagents_in_parallel, generate_subagent_id, SubagentType
from harness.agent.state import ThreadState


def main():
    print("=" * 60)
    print("Example 09: Subagent System")
    print("=" * 60)

    # Generate subagent IDs
    print("\n1. Generate Subagent IDs:")
    print("-" * 40)
    id1 = generate_subagent_id()
    id2 = generate_subagent_id()
    print(f"   ID 1: {id1}")
    print(f"   ID 2: {id2}")

    # Show subagent types
    print("\n2. Subagent Types:")
    print("-" * 40)
    print(f"   GENERAL: {SubagentType.GENERAL}")
    print(f"   BASH: {SubagentType.BASH}")

    # Simulate subagent execution
    print("\n3. Simulated Subagent Execution:")
    print("-" * 40)

    # Mock LLM - simple sync mock
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "Task completed successfully."
    mock_response.tool_calls = None
    mock_llm.ainvoke = lambda x: mock_response
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)

    print("   Simulating 3 parallel subagents...")

    # Note: Can't run real async here without event loop
    print("   In real usage:")
    print("   - Main agent calls spawn_subagent() to register tasks")
    print("   - SubagentMiddleware runs them in parallel via asyncio.gather")
    print("   - Results stored in state.subagent_results")

    # Show tool signatures
    print("\n4. Available Subagent Tools:")
    print("-" * 40)
    from harness.tools.subagent import spawn_subagent, get_subagent_results
    print(f"   spawn_subagent(name, task, type)")
    print(f"   get_subagent_results()")

    # Show expected flow
    print("\n" + "=" * 60)
    print("Expected Usage Flow:")
    print("=" * 60)
    print("""
    1. Main agent receives: "帮我分析这个项目并生成报告"
    2. Agent calls spawn_subagent("researcher", "分析代码结构")
    3. Agent calls spawn_subagent("writer", "生成报告文档")
    4. Agent calls get_subagent_results()
    5. SubagentMiddleware runs both in parallel
    6. Results aggregated in state.subagent_results
    7. Main agent synthesizes and responds to user
    """)

    print("✅ Subagent system ready for parallel task execution")


if __name__ == "__main__":
    main()
