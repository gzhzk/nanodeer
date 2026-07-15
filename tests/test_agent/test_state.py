"""Tests for AgentState compatibility and durable run outcomes."""

import pytest

from nanodeer.agent.state import (
    ThreadState,
    NextAction,
    SandboxState,
    WaitState,
)


class TestNextAction:
    def test_enum_values(self):
        assert NextAction.FINISH == "finish"
        assert NextAction.WAIT == "wait"
        assert len(NextAction) == 2


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
        assert t.next_action is None
        assert t.wait is None
        assert t.title is None

    def test_with_values(self):
        t = ThreadState(
            thread_id="thread-1",
            next_action=NextAction.FINISH,
            title="Test",
        )
        assert t.thread_id == "thread-1"
        assert t.next_action == NextAction.FINISH
        assert t.title == "Test"

    def test_runtime_resources_and_prompt_cache_are_not_state_fields(self):
        assert "sandbox" not in ThreadState.model_fields
        assert "system_prompt" not in ThreadState.model_fields


def test_wait_state_has_durable_resume_contract():
    wait_state = WaitState(
        question="Which account should I use?",
        required_input="account id",
        tool_call_id="call-wait",
        reason="missing_external_input",
    )

    restored = WaitState.model_validate_json(wait_state.model_dump_json())

    assert restored == wait_state
    assert restored.created_at_ms > 0
    assert restored.reason == "missing_external_input"
