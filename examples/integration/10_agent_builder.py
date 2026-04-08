"""Example 10: AgentBuilder - Building LangGraph Agent.

Demonstrates:
- Creating AgentBuilder with LLM and tools
- Building compiled StateGraph
- How agent node and tools node connect
"""
from unittest.mock import MagicMock
from harness.agent import AgentBuilder, ThreadState
from harness.agent.prompt import build_lead_agent_prompt


def main():
    print("=" * 60)
    print("Example 10: AgentBuilder")
    print("=" * 60)

    # Mock LLM
    mock_llm = MagicMock()
    print("\n1. Created mock LLM")

    # Create builder
    from harness.tools.file import read_file, write_file

    builder = AgentBuilder(
        llm=mock_llm,
        tools=[read_file, write_file],
    )
    print("2. Created AgentBuilder with 2 tools")

    # Build graph
    graph = builder.build()
    print("3. Built compiled StateGraph")
    print(f"   Graph type: {type(graph).__name__}")

    print("\n" + "=" * 60)
    print("Graph Structure:")
    print("=" * 60)
    print("""
    ┌─────────────┐
    │   (START)   │
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │   agent     │ ← LLM decides: tool call or end?
    │  (LLM)      │
    └──────┬──────┘
           │
     tool_calls?
           │
    ┌──────┴──────┐
    │             │
    ▼             ▼
  [END]       ┌─────────────┐
              │   tools     │ ← Execute tools
              └──────┬──────┘
                     │
                     ▼
                 (loop back to agent)
    """)

    # Check builder internals
    print("\n4. Builder internals:")
    print(f"   LLM: {builder.llm}")
    print(f"   Tools: {[t.name for t in builder._raw_tools]}")
    print(f"   Tool map keys: {list(builder._tool_map.keys())}")

    # Show system prompt
    prompt = build_lead_agent_prompt(
        tools=["ReadFile", "WriteFile"],
        thread_id="demo-thread",
    )
    print("\n5. System prompt preview:")
    print("-" * 40)
    print(prompt[:400] + "...")

    print("\n✅ AgentBuilder constructs the LangGraph state machine")


if __name__ == "__main__":
    main()
