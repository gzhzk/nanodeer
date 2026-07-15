import json

import pytest

from nanodeer.agent.tooling import execute_tool
from nanodeer.tools.tasks import tasks


@pytest.fixture
def task_store(tmp_path, monkeypatch):
    path = tmp_path / "daily" / "tasks.json"
    monkeypatch.setenv("NANODEER_TASKS_PATH", str(path))
    return path


def _id(result: str) -> str:
    return result.split(": ", 1)[1].split(" ", 1)[0]


def test_task_lifecycle_is_persistent(task_store):
    added = tasks.invoke({
        "action": "add",
        "title": "Prepare weekly review",
        "due": "2026-07-20",
        "notes": "Bring metrics",
    })
    task_id = _id(added)

    listed = tasks.invoke({"action": "list"})
    assert task_id in listed
    assert "due=2026-07-20" in listed

    updated = tasks.invoke({"action": "update", "task_id": task_id, "title": "Prepare review"})
    assert updated.endswith("Prepare review")
    completed = tasks.invoke({"action": "complete", "task_id": task_id})
    assert completed.startswith("Task completed")
    assert tasks.invoke({"action": "list"}) == "No tasks"
    assert "[x]" in tasks.invoke({"action": "list", "include_completed": True})

    deleted = tasks.invoke({"action": "delete", "task_id": task_id})
    assert deleted == f"Task deleted: {task_id}"
    assert json.loads(task_store.read_text())["tasks"] == []


@pytest.mark.asyncio
async def test_add_is_idempotent_for_a_durable_tool_call_id(task_store):
    call = {
        "id": "call-task-1",
        "name": "tasks",
        "args": {"action": "add", "title": "Book dentist"},
    }
    first = await execute_tool(tasks, call, exec_id=None)
    second = await execute_tool(tasks, call, exec_id=None)

    assert first.success is True
    assert second.success is True
    assert "already added" in second.content
    assert len(json.loads(task_store.read_text())["tasks"]) == 1


def test_tasks_reject_invalid_date_and_missing_identifiers(task_store):
    invalid = tasks.invoke({"action": "add", "title": "Bad date", "due": "next someday"})
    missing = tasks.invoke({"action": "complete"})

    assert invalid.startswith("Error managing tasks: due must be an ISO date")
    assert missing == "Error: task_id is required to complete a task"


def test_tasks_schema_is_one_compact_boundary():
    schema = tasks.get_input_schema().model_json_schema()
    assert {"action", "title", "task_id", "due", "notes", "include_completed"} <= set(
        schema["properties"]
    )
    assert schema["required"] == ["action"]
