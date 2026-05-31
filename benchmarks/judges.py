"""Deterministic assertions for benchmark task results."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nanodeer.agent.state import NextAction
from nanodeer.engine import RunResult

from .types import AssertionResult, BenchmarkTask


def evaluate_assertions(
    task: BenchmarkTask,
    result: RunResult,
    *,
    workspace: Path,
) -> list[AssertionResult]:
    """Evaluate deterministic assertions against a completed run."""
    return [_evaluate_one(assertion, result, workspace=workspace) for assertion in task.assertions]


def _evaluate_one(assertion: dict[str, Any], result: RunResult, *, workspace: Path) -> AssertionResult:
    kind = assertion.get("type", "")
    try:
        if kind == "output_contains":
            return _assert_output_contains(assertion, result)
        if kind == "tool_called":
            return _assert_tool_called(assertion, result)
        if kind == "tool_called_any":
            return _assert_tool_called_any(assertion, result)
        if kind == "trace_has":
            return _assert_trace_has(assertion, result)
        if kind == "trace_contract":
            return _assert_trace_contract(assertion, result)
        if kind == "tool_result_contains":
            return _assert_tool_result_contains(assertion, result)
        if kind == "file_exists":
            return _assert_file_exists(assertion, workspace)
        if kind == "file_contains":
            return _assert_file_contains(assertion, workspace)
        if kind == "metric_eq":
            return _assert_metric_compare(assertion, result, op="eq")
        if kind == "metric_lte":
            return _assert_metric_compare(assertion, result, op="lte")
        if kind == "metric_gte":
            return _assert_metric_compare(assertion, result, op="gte")
        if kind == "next_action_is":
            return _assert_next_action(assertion, result)
        if kind == "no_tool_errors":
            return _assert_no_tool_errors(result)
        return AssertionResult(False, kind or "unknown", f"Unknown assertion type: {kind!r}")
    except Exception as exc:
        return AssertionResult(False, kind or "unknown", f"Assertion raised {type(exc).__name__}: {exc}")


def _tool_names(result: RunResult) -> list[str]:
    return [str(call.get("name")) for call in result.tool_calls]


def _event_names(result: RunResult) -> list[str]:
    return [str(event.get("event") or event.get("type")) for event in result.events]


def _assert_output_contains(assertion: dict[str, Any], result: RunResult) -> AssertionResult:
    text = str(assertion.get("text", ""))
    passed = text in result.message
    return AssertionResult(passed, "output_contains", f"Output contains {text!r}: {passed}")


def _assert_tool_called(assertion: dict[str, Any], result: RunResult) -> AssertionResult:
    name = str(assertion.get("name", ""))
    tools = _tool_names(result)
    passed = name in tools
    return AssertionResult(passed, "tool_called", f"Tool {name!r} called: {passed} (tools={tools})")


def _assert_tool_called_any(assertion: dict[str, Any], result: RunResult) -> AssertionResult:
    names = [str(name) for name in assertion.get("names", [])]
    tools = _tool_names(result)
    matched = sorted(set(names) & set(tools))
    passed = bool(matched)
    return AssertionResult(
        passed,
        "tool_called_any",
        f"Any tool from {names!r} called: {passed} (matched={matched}, tools={tools})",
    )


def _assert_trace_has(assertion: dict[str, Any], result: RunResult) -> AssertionResult:
    event = str(assertion.get("event", ""))
    events = _event_names(result)
    passed = event in events
    return AssertionResult(passed, "trace_has", f"Trace has {event!r}: {passed}")


def _assert_trace_contract(assertion: dict[str, Any], result: RunResult) -> AssertionResult:
    """Validate the minimal observability contract for a completed run."""
    require_end = assertion.get("require_end", True)
    require_thread = assertion.get("require_thread", True)
    errors: list[str] = []
    events = result.events

    for index, event in enumerate(events):
        name = event.get("event") or event.get("type")
        if not name:
            errors.append(f"event[{index}] missing event/type")
            continue
        if event.get("event") != event.get("type"):
            errors.append(f"event[{index}] {name}: event/type mismatch")
        if event.get("schema_version") != "nanodeer.trace.v1":
            errors.append(f"event[{index}] {name}: missing schema_version")
        if "ts_ms" not in event:
            errors.append(f"event[{index}] {name}: missing ts_ms")
        if require_thread and "threadId" not in event:
            errors.append(f"event[{index}] {name}: missing threadId")
        if name not in {"end", "cancelled", "error"} and _event_needs_turn(name) and "turn" not in event:
            errors.append(f"event[{index}] {name}: missing turn")

    if require_end and not any((event.get("event") or event.get("type")) == "end" for event in events):
        errors.append("missing end event")

    llm_starts = _count_by_turn(events, "llm_start")
    llm_ends = _count_by_turn(events, "llm_end")
    for turn, count in llm_starts.items():
        if llm_ends.get(turn, 0) != count:
            errors.append(
                f"turn {turn}: llm_start count {count} != llm_end count {llm_ends.get(turn, 0)}"
            )

    tool_calls = _tool_event_keys(events, "tool_call")
    tool_results = _tool_event_keys(events, "tool_result")
    for key in tool_calls:
        if key not in tool_results:
            errors.append(f"tool_call without tool_result: {key}")

    acquired = [event for event in events if (event.get("event") or event.get("type")) == "sandbox_acquired"]
    released = [event for event in events if (event.get("event") or event.get("type")) == "sandbox_released"]
    if acquired and require_end and not released:
        errors.append("sandbox_acquired without sandbox_released")

    passed = not errors
    preview = "; ".join(errors[:5])
    if len(errors) > 5:
        preview += f"; ... {len(errors) - 5} more"
    return AssertionResult(
        passed,
        "trace_contract",
        "Trace contract valid" if passed else f"Trace contract failed: {preview}",
    )


def _event_needs_turn(name: str) -> bool:
    return name in {
        "turn_start",
        "context_loaded",
        "memory_context",
        "plan_context",
        "sandbox_acquired",
        "sandbox_released",
        "llm_start",
        "llm_retry",
        "llm_end",
        "reasoning_token",
        "llm_token",
        "assistant_response",
        "tool_call",
        "tool_blocked",
        "tool_result",
        "checkpoint_saved",
        "context_absorbed",
        "wait",
    }


def _count_by_turn(events: list[dict[str, Any]], name: str) -> dict[Any, int]:
    counts: dict[Any, int] = {}
    for event in events:
        event_name = event.get("event") or event.get("type")
        if event_name == name:
            turn = event.get("turn")
            counts[turn] = counts.get(turn, 0) + 1
    return counts


def _tool_event_keys(events: list[dict[str, Any]], name: str) -> set[tuple[Any, Any, Any, Any]]:
    keys = set()
    for event in events:
        event_name = event.get("event") or event.get("type")
        if event_name != name:
            continue
        keys.add((
            event.get("turn"),
            event.get("call_index"),
            event.get("id"),
            event.get("name"),
        ))
    return keys


def _assert_tool_result_contains(assertion: dict[str, Any], result: RunResult) -> AssertionResult:
    text = str(assertion.get("text", ""))
    tool_name = assertion.get("name")
    matches = []
    for event in result.events:
        name = event.get("event") or event.get("type")
        if name != "tool_result":
            continue
        if tool_name and event.get("name") != tool_name:
            continue
        if text in str(event.get("result", "")):
            matches.append(event.get("name"))
    passed = bool(matches)
    return AssertionResult(
        passed,
        "tool_result_contains",
        f"Tool result contains {text!r}: {passed} (matches={matches})",
    )


def _safe_workspace_path(workspace: Path, rel_path: str) -> Path:
    target = (workspace / rel_path).resolve()
    workspace = workspace.resolve()
    if target != workspace and workspace not in target.parents:
        raise ValueError(f"Path escapes workspace: {rel_path}")
    return target


def _assert_file_exists(assertion: dict[str, Any], workspace: Path) -> AssertionResult:
    path = str(assertion.get("path", ""))
    target = _safe_workspace_path(workspace, path)
    passed = target.exists()
    return AssertionResult(passed, "file_exists", f"File exists {path!r}: {passed}")


def _assert_file_contains(assertion: dict[str, Any], workspace: Path) -> AssertionResult:
    path = str(assertion.get("path", ""))
    text = str(assertion.get("text", ""))
    target = _safe_workspace_path(workspace, path)
    content = target.read_text(encoding="utf-8") if target.exists() else ""
    passed = text in content
    return AssertionResult(passed, "file_contains", f"File {path!r} contains {text!r}: {passed}")


def _assert_metric_compare(assertion: dict[str, Any], result: RunResult, *, op: str) -> AssertionResult:
    key = str(assertion.get("key", ""))
    expected = assertion.get("value")
    actual = result.metrics.get(key)
    if op == "eq":
        passed = actual == expected
        label = "=="
    elif op == "lte":
        passed = actual is not None and actual <= expected
        label = "<="
    else:
        passed = actual is not None and actual >= expected
        label = ">="
    return AssertionResult(passed, f"metric_{op}", f"Metric {key} {label} {expected}: {passed} (actual={actual})")


def _assert_next_action(assertion: dict[str, Any], result: RunResult) -> AssertionResult:
    expected = str(assertion.get("value", "end")).lower()
    actual = result.next_action.value if isinstance(result.next_action, NextAction) else str(result.next_action)
    passed = actual == expected
    return AssertionResult(passed, "next_action_is", f"Next action is {expected!r}: {passed} (actual={actual!r})")


def _assert_no_tool_errors(result: RunResult) -> AssertionResult:
    actual = result.metrics.get("num_tool_errors", 0)
    passed = actual == 0
    return AssertionResult(passed, "no_tool_errors", f"No tool errors: {passed} (actual={actual})")
