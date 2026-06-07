from pathlib import Path

from nanodeer.agent.state import NextAction
from nanodeer.engine import RunResult

from evaluation.judges import evaluate_assertions
from evaluation.types import EvaluationTask


def test_evaluate_trace_tool_metric_and_file_assertions(tmp_path: Path):
    (tmp_path / "summary.md").write_text("TOTAL_AMOUNT=65\n", encoding="utf-8")
    task = EvaluationTask(
        id="t",
        category="file_ops",
        prompt="",
        assertions=[
            {"type": "tool_called", "name": "write_file"},
            {"type": "trace_has", "event": "sandbox_acquired"},
            {"type": "file_contains", "path": "summary.md", "text": "TOTAL_AMOUNT=65"},
            {"type": "metric_eq", "key": "num_tool_errors", "value": 0},
            {"type": "next_action_is", "value": "end"},
        ],
    )
    result = RunResult(
        thread_id="thread",
        message="done",
        next_action=NextAction.END,
        tool_calls=[{"name": "write_file", "args": {}, "id": "call-1"}],
        events=[{"event": "sandbox_acquired"}],
        metrics={"num_tool_errors": 0},
    )

    assertions = evaluate_assertions(task, result, workspace=tmp_path)

    assert all(item.passed for item in assertions)


def test_file_assertion_blocks_workspace_escape(tmp_path: Path):
    task = EvaluationTask(
        id="t",
        category="file_ops",
        prompt="",
        assertions=[{"type": "file_exists", "path": "../outside.txt"}],
    )
    result = RunResult(thread_id="thread", message="")

    assertions = evaluate_assertions(task, result, workspace=tmp_path)

    assert assertions[0].passed is False
    assert "escapes workspace" in assertions[0].message


def test_trace_contract_passes_for_complete_run(tmp_path: Path):
    task = EvaluationTask(
        id="t",
        category="trace",
        prompt="",
        assertions=[{"type": "trace_contract"}],
    )
    result = RunResult(
        thread_id="thread",
        message="done",
        next_action=NextAction.END,
        events=[
            {
                "event": "turn_start",
                "type": "turn_start",
                "schema_version": "nanodeer.trace.v1",
                "ts_ms": 1,
                "threadId": "thread",
                "turn": 1,
            },
            {
                "event": "llm_start",
                "type": "llm_start",
                "schema_version": "nanodeer.trace.v1",
                "ts_ms": 2,
                "threadId": "thread",
                "turn": 1,
            },
            {
                "event": "llm_end",
                "type": "llm_end",
                "schema_version": "nanodeer.trace.v1",
                "ts_ms": 3,
                "threadId": "thread",
                "turn": 1,
            },
            {
                "event": "end",
                "type": "end",
                "schema_version": "nanodeer.trace.v1",
                "ts_ms": 4,
                "threadId": "thread",
                "turn": 1,
            },
        ],
    )

    assertions = evaluate_assertions(task, result, workspace=tmp_path)

    assert assertions[0].passed is True


def test_trace_contract_catches_missing_fields_and_orphan_tool_call(tmp_path: Path):
    task = EvaluationTask(
        id="t",
        category="trace",
        prompt="",
        assertions=[{"type": "trace_contract"}],
    )
    result = RunResult(
        thread_id="thread",
        message="done",
        events=[
            {
                "event": "tool_call",
                "type": "tool_call",
                "schema_version": "nanodeer.trace.v1",
                "ts_ms": 1,
                "turn": 1,
                "call_index": 0,
                "id": "call-1",
                "name": "write_file",
            },
            {
                "event": "end",
                "type": "end",
                "schema_version": "nanodeer.trace.v1",
                "ts_ms": 2,
                "threadId": "thread",
                "turn": 1,
            },
        ],
    )

    assertions = evaluate_assertions(task, result, workspace=tmp_path)

    assert assertions[0].passed is False
    assert "missing threadId" in assertions[0].message
    assert "tool_call without tool_result" in assertions[0].message


def test_quality_assertions_check_negative_output_tool_order_args_and_events(tmp_path: Path):
    (tmp_path / "result.json").write_text(
        '{"status": "ok", "metrics": {"count": 3}, "items": ["a", "b"]}',
        encoding="utf-8",
    )
    task = EvaluationTask(
        id="t",
        category="quality",
        prompt="",
        assertions=[
            {"type": "output_not_contains", "text": "PWNED"},
            {"type": "tool_not_called", "name": "save_memory"},
            {"type": "tool_sequence", "names": ["read_file", "write_file"]},
            {"type": "tool_args_contains", "name": "read_file", "text": "source.txt"},
            {"type": "event_order", "events": ["turn_start", "tool_call", "tool_result", "end"]},
            {"type": "file_json_value", "path": "result.json", "key": "metrics.count", "value": 3},
            {"type": "file_json_value", "path": "result.json", "key": "items.1", "value": "b"},
        ],
    )
    result = RunResult(
        thread_id="thread",
        message="SAFE_RESULT",
        next_action=NextAction.END,
        tool_calls=[
            {"name": "read_file", "args": {"file_path": "/mnt/user-data/source.txt"}, "id": "call-1"},
            {"name": "write_file", "args": {"file_path": "/mnt/user-data/result.json"}, "id": "call-2"},
        ],
        events=[
            {"event": "turn_start"},
            {"event": "tool_call"},
            {"event": "tool_result"},
            {"event": "end"},
        ],
    )

    assertions = evaluate_assertions(task, result, workspace=tmp_path)

    assert all(item.passed for item in assertions)


def test_file_not_exists_assertion(tmp_path: Path):
    task = EvaluationTask(
        id="t",
        category="quality",
        prompt="",
        assertions=[{"type": "file_not_exists", "path": "unexpected.txt"}],
    )
    result = RunResult(thread_id="thread", message="")

    assertions = evaluate_assertions(task, result, workspace=tmp_path)

    assert assertions[0].passed is True
