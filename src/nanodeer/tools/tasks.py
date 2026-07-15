"""Persistent personal task list exposed through one tool boundary."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool

from nanodeer.agent.tooling import current_tool_call_id

_LOCK = threading.Lock()


def _tasks_path() -> Path:
    override = os.getenv("NANODEER_TASKS_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".nanodeer" / "daily" / "tasks.json"


def _load(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "tasks": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise ValueError("task store has an invalid format")
    return data


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".tasks.", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_due(value: str) -> str:
    if not value:
        return ""
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("due must be an ISO date or datetime, for example 2026-07-20") from exc
    return value


def _find(items: list[dict], task_id: str) -> dict | None:
    return next((item for item in items if item.get("id") == task_id), None)


def _render(items: list[dict], include_completed: bool) -> str:
    visible = [item for item in items if include_completed or item.get("status") != "completed"]
    visible.sort(
        key=lambda item: (
            item.get("status") == "completed",
            item.get("due") or "9999-12-31",
            item.get("created_at") or "",
        )
    )
    if not visible:
        return "No tasks"
    lines = []
    for item in visible:
        marker = "x" if item.get("status") == "completed" else " "
        due = f" due={item['due']}" if item.get("due") else ""
        notes = f" — {item['notes']}" if item.get("notes") else ""
        lines.append(f"- [{marker}] {item['id']} {item['title']}{due}{notes}")
    return "\n".join(lines)


@tool
def tasks(
    action: Literal["add", "list", "update", "complete", "delete"],
    title: str = "",
    task_id: str = "",
    due: str = "",
    notes: str = "",
    include_completed: bool = False,
) -> str:
    """Manage the user's persistent lightweight task list.

    Args:
        action: Add, list, update, complete, or delete a task.
        title: Task title; required for add and optional for update.
        task_id: Stable id returned by add/list; required for update, complete, and delete.
        due: Optional ISO date or datetime such as ``2026-07-20``.
        notes: Optional compact task notes.
        include_completed: Include completed items when listing.
    """
    path = _tasks_path()
    try:
        with _LOCK:
            data = _load(path)
            items = data["tasks"]

            if action == "list":
                return _render(items, include_completed)

            if action == "add":
                title = title.strip()
                if not title:
                    return "Error: title is required to add a task"
                call_id = current_tool_call_id()
                if call_id:
                    existing = next(
                        (item for item in items if item.get("created_by_call_id") == call_id),
                        None,
                    )
                    if existing:
                        return f"Task already added: {existing['id']} {existing['title']}"
                item = {
                    "id": uuid.uuid4().hex[:10],
                    "title": title,
                    "due": _validate_due(due.strip()),
                    "notes": notes.strip(),
                    "status": "open",
                    "created_at": _now(),
                    "completed_at": None,
                }
                if call_id:
                    item["created_by_call_id"] = call_id
                items.append(item)
                _save(path, data)
                return f"Task added: {item['id']} {item['title']}"

            if not task_id:
                return f"Error: task_id is required to {action} a task"
            item = _find(items, task_id)
            if item is None:
                return f"Error: task not found: {task_id}"

            if action == "delete":
                items.remove(item)
                _save(path, data)
                return f"Task deleted: {task_id}"
            if action == "complete":
                item["status"] = "completed"
                item["completed_at"] = _now()
                _save(path, data)
                return f"Task completed: {task_id} {item['title']}"

            if title.strip():
                item["title"] = title.strip()
            if due.strip():
                item["due"] = _validate_due(due.strip())
            if notes.strip():
                item["notes"] = notes.strip()
            item["updated_at"] = _now()
            _save(path, data)
            return f"Task updated: {task_id} {item['title']}"
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return f"Error managing tasks: {exc}"


__all__ = ["tasks"]
