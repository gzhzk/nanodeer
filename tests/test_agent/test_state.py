"""Tests for ThreadState, TurnSignals, NextAction."""

import pytest

from nanodeer.agent.state import (
    ThreadState,
    TurnSignals,
    NextAction,
    SandboxState,
    merge_todos,
    merge_artifacts,
)


class TestNextAction:
    def test_enum_values(self):
        assert NextAction.PROCESS == "process"
        assert NextAction.WAIT == "wait"
        assert NextAction.END == "end"


class TestSandboxState:
    def test_default_fields(self):
        s = SandboxState()
        assert s.exec_id is None
        assert s.container_id is None
        assert s.working_dir is None
        assert s.status is None

    def test_set_fields(self):
        s = SandboxState(exec_id="abc", container_id="cnt-123", working_dir="/workspace/abc", status="ready")
        assert s.exec_id == "abc"
        assert s.container_id == "cnt-123"
        assert s.working_dir == "/workspace/abc"
        assert s.status == "ready"


class TestThreadState:
    def test_defaults(self):
        t = ThreadState()
        assert t.thread_id is None
        assert t.messages == []
        assert t.next_action == NextAction.PROCESS
        assert t.todos == []
        assert t.artifacts == []
        assert t.title is None
        assert t.sandbox is None

    def test_with_values(self):
        t = ThreadState(
            thread_id="thread-1",
            next_action=NextAction.END,
            title="Test",
        )
        assert t.thread_id == "thread-1"
        assert t.next_action == NextAction.END
        assert t.title == "Test"


class TestMergeTodos:
    def test_empty_both(self):
        assert merge_todos([], []) == []
        assert merge_todos(None, None) == []

    def test_new_only(self):
        new = [{"id": "1", "content": "A"}]
        assert merge_todos([], new) == new

    def test_existing_only(self):
        existing = [{"id": "1", "content": "A"}]
        assert merge_todos(existing, []) == existing

    def test_merge_by_id(self):
        existing = [{"id": "1", "content": "Old"}]
        new = [{"id": "2", "content": "New"}]
        result = merge_todos(existing, new)
        assert len(result) == 2
        ids = {r["id"] for r in result}
        assert ids == {"1", "2"}

    def test_idempotent(self):
        todos = [{"id": "1", "content": "A"}, {"id": "2", "content": "B"}]
        result = merge_todos(todos, todos)
        assert len(result) == 2

    def test_replaces_id_if_conflict(self):
        existing = [{"id": "1", "content": "Old"}]
        new = [{"id": "1", "content": "New"}]
        result = merge_todos(existing, new)
        assert len(result) == 1
        assert result[0]["content"] == "New"


class TestMergeArtifacts:
    def test_empty(self):
        assert merge_artifacts([], []) == []
        assert merge_artifacts(None, None) == []

    def test_new_only(self):
        new = ["/path/a.txt"]
        assert merge_artifacts([], new) == new

    def test_existing_only(self):
        existing = ["/path/a.txt"]
        assert merge_artifacts(existing, []) == existing

    def test_deduplicate(self):
        existing = ["/path/a.txt", "/path/b.txt"]
        new = ["/path/b.txt", "/path/c.txt"]
        result = merge_artifacts(existing, new)
        assert len(result) == 3
        # Order: existing first, then new items not in existing
        assert result == ["/path/a.txt", "/path/b.txt", "/path/c.txt"]

    def test_empty_returns_new(self):
        assert merge_artifacts([], ["/path/a.txt"]) == ["/path/a.txt"]


class TestTurnSignals:
    def test_defaults(self):
        s = TurnSignals()
        assert s.clarification_question is None
        assert s.memory_context is None
        assert s.error is None

    def test_with_values(self):
        s = TurnSignals(
            clarification_question="Which format?",
            memory_context="User prefers JSON",
            error={"type": "sandbox_released", "detail": "container gone"},
        )
        assert s.clarification_question == "Which format?"
        assert s.memory_context == "User prefers JSON"
        assert s.error == {"type": "sandbox_released", "detail": "container gone"}