"""Pydantic models for NanoDeer API requests and responses."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    """Request to run the agent with a prompt."""

    prompt: str = Field(..., description="User prompt / task description")
    thread_id: str | None = Field(
        default=None, description="Thread ID for multi-turn. Auto-created if None."
    )
    upload_ids: list[str] = Field(
        default_factory=list,
        description="Upload IDs from prior /upload calls to attach.",
    )
    model: str | None = Field(
        default=None, description="Override default model."
    )
    system_hint: str | None = Field(
        default=None, description="Extra system-level instruction."
    )


class ToolCallDelta(BaseModel):
    """A single tool call delta in the stream."""

    tool: str
    input: dict[str, Any]
    output: str | None = None
    error: str | None = None


class RunResponse(BaseModel):
    """Response from a completed agent run."""

    thread_id: str
    message: str
    artifacts: list[str] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


class UploadResponse(BaseModel):
    """Response after file upload."""

    upload_id: str
    filename: str
    size_bytes: int
    content_type: str | None


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------


class ScheduleCreate(BaseModel):
    """Create a new scheduled job."""

    name: str = Field(..., description="Human-readable job name")
    prompt: str = Field(..., description="Prompt to run on schedule")
    cron: str = Field(..., description="Crontab expression, e.g. '0 9 * * *'")
    thread_id: str | None = Field(
        default=None,
        description="Thread ID to use. Auto-created per-run if None.",
    )


class ScheduleItem(BaseModel):
    """A registered scheduled job."""

    id: str
    name: str
    prompt: str
    cron: str
    thread_id: str | None
    enabled: bool = True
    created_at: datetime
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    run_count: int = 0


class ScheduleListResponse(BaseModel):
    """List of all schedules."""

    schedules: list[ScheduleItem]


# ---------------------------------------------------------------------------
# Threads
# ---------------------------------------------------------------------------


class ThreadSummary(BaseModel):
    """Summary of a thread."""

    thread_id: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    preview: str  # first 200 chars of last message


class ThreadListResponse(BaseModel):
    """List of threads."""

    threads: list[ThreadSummary]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str
