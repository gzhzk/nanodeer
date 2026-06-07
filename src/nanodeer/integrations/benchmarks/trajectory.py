"""Convert NanoDeer run results into a benchmark-friendly trajectory file."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from nanodeer.engine import RunResult


def _iso_from_ms(ts_ms: int | None) -> str:
    if not ts_ms:
        return datetime.now(timezone.utc).isoformat()
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def _first_ts(events: list[dict[str, Any]]) -> int | None:
    for event in events:
        ts_ms = event.get("ts_ms")
        if isinstance(ts_ms, int):
            return ts_ms
    return None


def nanodeer_result_to_atif(
    *,
    instruction: str,
    result: RunResult,
    agent_name: str = "nanodeer",
    agent_version: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    """Build a compact ATIF-style trajectory from NanoDeer trace events."""
    steps: list[dict[str, Any]] = [
        {
            "step_id": 1,
            "timestamp": _iso_from_ms(_first_ts(result.events)),
            "source": "user",
            "message": instruction,
        }
    ]

    pending_calls: dict[tuple[int | None, str | None], dict[str, Any]] = {}
    for event in result.events:
        event_name = event.get("event") or event.get("type")
        key = (event.get("call_index"), event.get("id"))
        if event_name == "tool_call":
            pending_calls[key] = event
            continue
        if event_name != "tool_result":
            continue

        call = pending_calls.pop(key, {})
        tool_name = event.get("name") or call.get("name") or "tool"
        call_id = str(event.get("id") or call.get("id") or f"call-{len(steps)}")
        args = call.get("args") or call.get("args_preview") or {}
        if not isinstance(args, dict):
            args = {"value": args}

        steps.append(
            {
                "step_id": len(steps) + 1,
                "timestamp": _iso_from_ms(event.get("ts_ms") or call.get("ts_ms")),
                "source": "agent",
                "message": f"Executed {tool_name}",
                "model_name": model_name,
                "tool_calls": [
                    {
                        "tool_call_id": call_id,
                        "function_name": str(tool_name),
                        "arguments": args,
                    }
                ],
                "observation": {
                    "results": [
                        {
                            "source_call_id": call_id,
                            "content": str(event.get("result") or event.get("result_preview") or ""),
                            "extra": {
                                "success": bool(event.get("success", True)),
                                "duration_ms": event.get("duration_ms"),
                            },
                        }
                    ]
                },
            }
        )

    if result.message:
        steps.append(
            {
                "step_id": len(steps) + 1,
                "timestamp": _iso_from_ms(None),
                "source": "agent",
                "message": result.message,
                "model_name": model_name,
            }
        )

    metrics = result.metrics or {}
    return {
        "schema_version": "ATIF-v1.7",
        "session_id": result.thread_id,
        "agent": {
            "name": agent_name,
            "version": agent_version,
            "model_name": model_name,
        },
        "steps": steps,
        "final_metrics": {
            "total_prompt_tokens": metrics.get("input_tokens") or None,
            "total_completion_tokens": metrics.get("output_tokens") or None,
            "total_cached_tokens": metrics.get("cached_tokens") or None,
            "total_steps": len(steps),
            "extra": {
                "total_tokens": metrics.get("total_tokens"),
                "duration_ms": result.duration_ms,
                "num_turns": metrics.get("num_turns"),
                "num_tool_calls": metrics.get("num_tool_calls"),
                "num_tool_errors": metrics.get("num_tool_errors"),
            },
        },
    }

