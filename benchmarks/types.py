"""Types used by the lightweight NanoDeer benchmark runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BenchmarkTask:
    id: str
    category: str
    prompt: str
    description: str = ""
    setup: dict[str, Any] = field(default_factory=dict)
    assertions: list[dict[str, Any]] = field(default_factory=list)
    turns: list[str] = field(default_factory=list)


@dataclass
class AssertionResult:
    passed: bool
    type: str
    message: str


@dataclass
class TaskResult:
    task_id: str
    category: str
    success: bool
    duration_ms: int
    metrics: dict[str, Any]
    tool_calls: list[str]
    assertions: list[AssertionResult]
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    thread_id: str | None = None
    workspace: Path | None = None
    trace_dir: Path | None = None


@dataclass
class BenchmarkReport:
    config: dict[str, Any]
    results: list[TaskResult]
    summary: dict[str, Any]
