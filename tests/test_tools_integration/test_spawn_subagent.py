"""Tests for subagent tools."""

import importlib

import pytest

spawn_subagent_module = importlib.import_module("nanodeer.tools.spawn_subagent")
get_subagent_results = spawn_subagent_module.get_subagent_results


class _Worker:
    def __init__(self, worker_id: str):
        self.worker_id = worker_id


class _Coordinator:
    def __init__(self, *, pending=None, active=None, completed=None):
        self._pending = pending or []
        self._active = active or []
        self._completed = completed or {}

    def get_result(self, sub_id: str):
        return self._completed.get(sub_id)

    def list_pending(self):
        return self._pending

    def list_active(self):
        return self._active


@pytest.mark.asyncio
async def test_get_subagent_results_pending_is_not_not_found(monkeypatch):
    """Pending workers should be reported as running, not as missing."""
    coord = _Coordinator(pending=[_Worker("wkr-123")])
    monkeypatch.setattr(spawn_subagent_module, "get_executor", lambda: coord)

    result = await get_subagent_results.ainvoke({"sub_id": "wkr-123"})

    assert result == "Subagent wkr-123 is still running."


@pytest.mark.asyncio
async def test_get_subagent_results_unknown_is_error(monkeypatch):
    """Unknown workers should be explicit errors."""
    coord = _Coordinator()
    monkeypatch.setattr(spawn_subagent_module, "get_executor", lambda: coord)

    result = await get_subagent_results.ainvoke({"sub_id": "wkr-missing"})

    assert result == "Error: Subagent wkr-missing not found."
