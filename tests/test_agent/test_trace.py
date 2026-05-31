import json

from nanodeer.agent.trace import TRACE_SCHEMA_VERSION, TraceCollector, make_trace_event, preview


def test_make_trace_event_adds_envelope_fields():
    event = make_trace_event("llm_start", threadId="t1", turn=1)

    assert event["event"] == "llm_start"
    assert event["type"] == "llm_start"
    assert event["schema_version"] == TRACE_SCHEMA_VERSION
    assert event["threadId"] == "t1"
    assert event["turn"] == 1
    assert isinstance(event["ts_ms"], int)


def test_trace_collector_emit_collects_events_with_thread_id():
    collector = TraceCollector(thread_id="thread-1")

    event = collector.emit("tool_call", turn=2, name="read_file")

    assert event["threadId"] == "thread-1"
    assert event["run_id"] == collector.run_id
    assert collector.events == [event]


def test_trace_collector_normalize_fills_missing_defaults():
    collector = TraceCollector(thread_id="thread-1")

    event = collector.normalize({"type": "memory_context", "has_memory": True}, turn=3)

    assert event["event"] == "memory_context"
    assert event["type"] == "memory_context"
    assert event["threadId"] == "thread-1"
    assert event["run_id"] == collector.run_id
    assert event["turn"] == 3
    assert event["schema_version"] == TRACE_SCHEMA_VERSION


def test_trace_collector_normalize_repairs_bad_envelope_fields():
    collector = TraceCollector(thread_id="thread-1")

    event = collector.normalize(
        {"type": "memory_context", "schema_version": "old", "ts_ms": None},
        turn=1,
    )

    assert event["schema_version"] == TRACE_SCHEMA_VERSION
    assert isinstance(event["ts_ms"], int)


def test_preview_truncates_nested_values():
    value = {"long": "x" * 10, "items": ["y" * 10]}

    assert preview(value, limit=3) == {"long": "xxx...[truncated]", "items": ["yyy...[truncated]"]}


def test_trace_collector_can_persist_jsonl(tmp_path):
    collector = TraceCollector(
        thread_id="thread-1",
        run_id="run-1",
        trace_root=tmp_path,
        persist=True,
    )

    collector.emit("turn_start", turn=1)
    collector.normalize({"type": "memory_context", "has_memory": False}, turn=1)

    assert collector.path == tmp_path / "thread-1" / "run-1.jsonl"
    rows = [
        json.loads(line)
        for line in collector.path.read_text(encoding="utf-8").splitlines()
    ]
    assert [row["event"] for row in rows] == ["turn_start", "memory_context"]
    assert all(row["threadId"] == "thread-1" for row in rows)
    assert all(row["run_id"] == "run-1" for row in rows)
