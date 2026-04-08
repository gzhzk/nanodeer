"""Example 08: Plan mode - task tracking and planning.

Run with: python -m examples.08_plan

This example demonstrates:
- TodoItem data structure and markdown formatting
- TodoListMiddleware integration with MemoryStore
- before_agent_start loads todos from storage
- after_agent_end saves todos to storage
- write_todo tool usage
"""

import asyncio
import tempfile
from pathlib import Path

from harness.plan import TodoItem, TodoStatus
from harness.tools import write_todo, list_todos, complete_todo
from harness.middlewares import TodoListMiddleware
from harness.memory import MemoryStore


async def demo_todo_item():
    """Demo: TodoItem creation and markdown formatting."""
    print("\n=== TodoItem Demo ===")

    # Create todos with different statuses
    todos = [
        TodoItem(content="Design the architecture", status=TodoStatus.COMPLETED),
        TodoItem(content="Implement core agent", status=TodoStatus.IN_PROGRESS),
        TodoItem(content="Write tests", status=TodoStatus.PENDING),
    ]

    for todo in todos:
        print(f"  {todo.to_markdown()}")


async def demo_todo_list_middleware():
    """Demo: TodoListMiddleware integration."""
    print("\n=== TodoListMiddleware Demo ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(root=Path(tmpdir))

        # Pre-save some todos
        store.save_todos("user1", "project1", [
            {"content": "Design the architecture", "status": "completed"},
            {"content": "Implement core agent", "status": "in_progress"},
            {"content": "Write documentation", "status": "pending"},
        ])
        print("Saved 3 todos for user1/project1")

        # Create middleware
        middleware = TodoListMiddleware(store, project_slug="project1")

        # Simulate before_agent_start - loads todos into state
        state = {"thread_id": "user1", "todos": []}
        await middleware.before_agent_start(state)

        print(f"\nLoaded {len(state['todos'])} todos into state:")
        for todo in state["todos"]:
            status_icon = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}[todo["status"]]
            print(f"  {status_icon} {todo['content']}")

        # Simulate adding a new todo
        new_todo = TodoItem(content="Deploy to production", status=TodoStatus.PENDING)
        state["todos"].append(new_todo.to_dict())

        # Simulate after_agent_end - saves todos to storage
        result = {"thread_id": "user1", "todos": state["todos"]}
        await middleware.after_agent_end(result)

        # Verify saved
        loaded = store.load_todos("user1", "project1")
        print(f"\nVerified: {len(loaded)} todos saved to storage")


async def demo_write_todo_tool():
    """Demo: write_todo tool."""
    print("\n=== write_todo Tool Demo ===")

    # Create a todo using the tool
    result = write_todo.invoke({
        "content": "Review pull requests",
        "status": "pending",
        "priority": 1,
    })

    print(f"Tool output:\n  {result}")


async def main():
    print("=" * 60)
    print("NanoDeer Plan Mode Demo")
    print("=" * 60)

    await demo_todo_item()
    await demo_todo_list_middleware()
    await demo_write_todo_tool()

    print("\n" + "=" * 60)
    print("✅ All plan demos passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
