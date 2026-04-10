"""Plan mode types for NanoDeer."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal


class TodoStatus(str, Enum):
    """Todo status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class TodoItem:
    """A single todo item for task tracking.

    Attributes:
        id: Unique identifier (format: todo-{timestamp}-{random}).
        content: Task description.
        status: Current status.
        priority: Priority level (higher = more important).
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """
    content: str
    status: TodoStatus = TodoStatus.PENDING
    priority: int = 0
    id: str = field(default_factory=lambda: f"todo-{datetime.now().timestamp()}")
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_markdown(self) -> str:
        """Convert to markdown checkbox format."""
        checkbox = "[ ]" if self.status == TodoStatus.PENDING else "[ ]"
        if self.status == TodoStatus.IN_PROGRESS:
            checkbox = "[>]"
        elif self.status == TodoStatus.COMPLETED:
            checkbox = "[x]"
        return f"{checkbox} {self.content}"

    @classmethod
    def from_dict(cls, data: dict) -> "TodoItem":
        """Create from dictionary."""
        return cls(
            id=data.get("id", f"todo-{datetime.now().timestamp()}"),
            content=data.get("content", ""),
            status=TodoStatus(data.get("status", "pending")),
            priority=data.get("priority", 0),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status.value,
            "priority": self.priority,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


TODOS_SECTION_TEMPLATE = """<todos>
{todos}
</todos>"""
