"""Types used by the lightweight NanoDeer evaluation runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EvaluationTask:
    id: str
    category: str
    prompt: str
    description: str = ""
    suite: str = ""
    level: str = ""
    capabilities: list[str] = field(default_factory=list)
    behaviors: list[str] = field(default_factory=list)
    scenario: str = ""
    budgets: dict[str, Any] = field(default_factory=dict)
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
    suite: str
    level: str
    success: bool
    duration_ms: int
    metrics: dict[str, Any]
    tool_calls: list[str]
    assertions: list[AssertionResult]
    capabilities: list[str] = field(default_factory=list)
    behaviors: list[str] = field(default_factory=list)
    scenario: str = ""
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    thread_id: str | None = None
    workspace: Path | None = None
    trace_dir: Path | None = None


@dataclass
class EvaluationReport:
    config: dict[str, Any]
    results: list[TaskResult]
    summary: dict[str, Any]
