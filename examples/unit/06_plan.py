"""Example 06: Plan/Todo - Task tracking.

Demonstrates:
- TodoItem creation
- TodoStatus enum values
- Markdown formatting
- Serialization/deserialization
"""
from harness.plan import TodoItem, TodoStatus


def main():
    print("=" * 60)
    print("Example 06: Plan/Todo System")
    print("=" * 60)

    # Create todos
    todo1 = TodoItem(content="Design the architecture", status=TodoStatus.COMPLETED)
    todo2 = TodoItem(content="Implement core features", status=TodoStatus.IN_PROGRESS, priority=2)
    todo3 = TodoItem(content="Write documentation", status=TodoStatus.PENDING, priority=1)

    print("\nTodo Items:")
    print("-" * 40)
    for todo in [todo1, todo2, todo3]:
        print(f"  {todo.to_markdown()}")
        print(f"    ID: {todo.id}, Priority: {todo.priority}")

    print("\nStatus Values:")
    print("-" * 40)
    print(f"  PENDING: {TodoStatus.PENDING.value}")
    print(f"  IN_PROGRESS: {TodoStatus.IN_PROGRESS.value}")
    print(f"  COMPLETED: {TodoStatus.COMPLETED.value}")

    # Serialization
    print("\nSerialization:")
    print("-" * 40)
    data = todo2.to_dict()
    print(f"  to_dict(): {data}")

    restored = TodoItem.from_dict(data)
    print(f"  from_dict(): {restored.to_markdown()}")

    # Status transitions
    print("\nStatus Transitions:")
    print("-" * 40)
    task = TodoItem(content="New task")
    print(f"  Created: {task.to_markdown()}")

    task.status = TodoStatus.IN_PROGRESS
    print(f"  Started: {task.to_markdown()}")

    task.status = TodoStatus.COMPLETED
    print(f"  Done: {task.to_markdown()}")

    print("\n✅ Todo system tracks multi-step task progress")


if __name__ == "__main__":
    main()
