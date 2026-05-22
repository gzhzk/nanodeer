"""Subagent types — WorkerTask, WorkerStatus, WorkerSpec."""

import uuid
from dataclasses import dataclass, field
from enum import Enum


class WorkerStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class WorkerSpec:
    """Optional configuration overrides for a worker."""
    max_iterations: int = 10
    timeout_seconds: int = 900
    model: str | None = None


@dataclass
class WorkerTask:
    """Represents a single subagent worker task."""
    worker_id: str = field(default_factory=lambda: f"wkr-{uuid.uuid4().hex[:8]}")
    name: str = "worker"
    task: str = ""
    status: WorkerStatus = WorkerStatus.PENDING
    output: str | None = None
    error: str | None = None
    created_at: float | None = None
    started_at: float | None = None
    completed_at: float | None = None
    duration_seconds: float = 0.0
    spec: WorkerSpec | None = None

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "name": self.name,
            "task": self.task,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
        }
