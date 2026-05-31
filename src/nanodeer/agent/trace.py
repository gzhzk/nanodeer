"""Trace event helpers for NanoDeer runtime observability."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

TRACE_SCHEMA_VERSION = "nanodeer.trace.v1"
TRACE_PREVIEW_CHARS = 500


def now_ms() -> int:
    return int(time.time() * 1000)


def preview(value: Any, limit: int = TRACE_PREVIEW_CHARS) -> Any:
    """Return a JSON-friendly, size-bounded value for trace payloads."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "...[truncated]"
    if isinstance(value, dict):
        return {str(k): preview(v, limit) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [preview(v, limit) for v in value[:20]]
    return preview(str(value), limit)


def make_trace_event(event: str, **fields) -> dict:
    """Create a normalized trace event dict."""
    payload = {
        "event": event,
        "type": event,
        "schema_version": TRACE_SCHEMA_VERSION,
        "ts_ms": now_ms(),
    }
    payload.update(fields)
    payload["event"] = event
    payload["type"] = event
    payload["schema_version"] = TRACE_SCHEMA_VERSION
    if not isinstance(payload.get("ts_ms"), int):
        payload["ts_ms"] = now_ms()
    return payload


def _trace_enabled() -> bool:
    value = os.getenv("NANODEER_TRACE_ENABLED", "")
    return value.lower() in {"1", "true", "yes", "on"} or bool(os.getenv("NANODEER_TRACE_ROOT"))


def _default_trace_root() -> Path:
    override = os.getenv("NANODEER_TRACE_ROOT")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".nanodeer" / "traces"


class TraceCollector:
    """Collect and normalize runtime trace events.

    The collector is intentionally small: it owns event envelope consistency,
    while callers still decide which domain fields belong on each event.
    """

    def __init__(
        self,
        *,
        thread_id: str,
        run_id: str | None = None,
        trace_root: str | Path | None = None,
        persist: bool | None = None,
    ):
        self.thread_id = thread_id
        self.run_id = run_id or uuid.uuid4().hex
        self._events: list[dict] = []
        self._persist = _trace_enabled() if persist is None else persist
        self._path: Path | None = None
        if self._persist:
            root = Path(trace_root).expanduser() if trace_root else _default_trace_root()
            self._path = root / self.thread_id / f"{self.run_id}.jsonl"
            self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def events(self) -> list[dict]:
        return self._events

    @property
    def path(self) -> Path | None:
        return self._path

    def emit(self, event: str, **fields) -> dict:
        fields.setdefault("threadId", self.thread_id)
        fields.setdefault("run_id", self.run_id)
        payload = make_trace_event(event, **fields)
        self._events.append(payload)
        self._write(payload)
        return payload

    def normalize(self, event: dict, **defaults) -> dict:
        name = event.get("event") or event.get("type") or "unknown"
        defaults.setdefault("run_id", self.run_id)
        normalized = make_trace_event(name, **defaults)
        normalized.update(event)
        normalized["event"] = name
        normalized["type"] = name
        normalized["schema_version"] = TRACE_SCHEMA_VERSION
        if not isinstance(normalized.get("ts_ms"), int):
            normalized["ts_ms"] = now_ms()
        normalized.setdefault("threadId", self.thread_id)
        normalized.setdefault("run_id", self.run_id)
        self._events.append(normalized)
        self._write(normalized)
        return normalized

    def _write(self, event: dict) -> None:
        if not self._path:
            return
        line = json.dumps(event, ensure_ascii=False, default=str)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
