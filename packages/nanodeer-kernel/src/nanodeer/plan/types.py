"""Plan types for NanoDeer — Plan is the aggregate root containing steps."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class StepStatus(str, Enum):
    """Step status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class PlanStatus(str, Enum):
    """Plan lifecycle status."""
    DRAFTING = "drafting"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Step:
    """A single step within a plan."""

    content: str
    status: StepStatus = StepStatus.PENDING
    id: str = field(default_factory=lambda: f"step-{uuid.uuid4().hex[:8]}")
    dependencies: list[str] = field(default_factory=list)
    assigned_to: str | None = None
    result: str | None = None
    notes: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def from_dict(cls, data: dict) -> "Step":
        return cls(
            id=data.get("id", f"step-{uuid.uuid4().hex[:8]}"),
            content=data.get("content", ""),
            status=StepStatus(data.get("status", "pending")),
            dependencies=data.get("dependencies", []),
            assigned_to=data.get("assigned_to"),
            result=data.get("result"),
            notes=data.get("notes"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "content": self.content,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.assigned_to:
            d["assigned_to"] = self.assigned_to
        if self.result:
            d["result"] = self.result
        if self.notes:
            d["notes"] = self.notes
        return d

    def to_markdown(self) -> str:
        checkbox = {
            StepStatus.PENDING: "[ ]",
            StepStatus.IN_PROGRESS: "[*]",
            StepStatus.COMPLETED: "[x]",
            StepStatus.BLOCKED: "[!]",
            StepStatus.FAILED: "[-]",
        }.get(self.status, "[ ]")
        return f"{checkbox} {self.content}"


@dataclass
class Plan:
    """A plan containing multiple steps."""

    plan_id: str
    goal: str
    title: str = ""
    status: PlanStatus = PlanStatus.DRAFTING
    steps: list[Step] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def from_dict(cls, data: dict) -> "Plan":
        return cls(
            plan_id=data.get("plan_id", ""),
            goal=data.get("goal", ""),
            title=data.get("title", ""),
            status=PlanStatus(data.get("status", "drafting")),
            steps=[Step.from_dict(s) for s in data.get("steps", [])],
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "title": self.title,
            "status": self.status.value,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)

    @property
    def total_count(self) -> int:
        return len(self.steps)

    @property
    def progress_pct(self) -> int:
        if not self.steps:
            return 0
        return self.completed_count * 100 // self.total_count
