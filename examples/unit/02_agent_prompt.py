"""Example 02: System Prompt Generation.

Demonstrates:
- build_lead_agent_prompt() with various parameters
- Tool section generation
- Todo formatting
- Memory context injection
"""
from harness.agent.prompt import (
    build_lead_agent_prompt,
    get_tools_section,
    format_todos,
)


def main():
    print("=" * 60)
    print("Example 02: System Prompt Generation")
    print("=" * 60)

    # Basic prompt
    prompt = build_lead_agent_prompt()
    print("\n1. Basic prompt (no tools):")
    print("-" * 40)
    print(prompt[:500] + "...")

    # Prompt with tools
    prompt = build_lead_agent_prompt(
        tools=["ReadFile", "WriteFile", "Bash", "Ls"],
        thread_id="user-123",
    )
    print("\n2. Prompt with tools and thread_id:")
    print("-" * 40)
    print(prompt[:600] + "...")

    # Prompt with memory context
    prompt = build_lead_agent_prompt(
        memory_context="User prefers Python over JavaScript."
    )
    print("\n3. Prompt with memory context:")
    print("-" * 40)
    assert "User prefers Python" in prompt
    print("Memory context injected ✓")

    # Prompt with todos
    todos = [
        {"content": "Design architecture", "status": "completed"},
        {"content": "Implement core features", "status": "in_progress"},
        {"content": "Write tests", "status": "pending"},
    ]
    todos_section = format_todos(todos)
    print("\n4. Todo format:")
    print("-" * 40)
    print(todos_section)

    print("\n✅ System prompt is built dynamically based on:")
    print("   - Available tools")
    print("   - Thread context")
    print("   - Memory context")
    print("   - Active todos")


if __name__ == "__main__":
    main()
