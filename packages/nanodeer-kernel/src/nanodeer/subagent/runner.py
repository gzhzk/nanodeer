"""Subagent runner — result formatting utilities."""

from typing import Any

from .types import WorkerTask


def format_result(result: dict[str, Any] | WorkerTask) -> str:
    """Format a subagent result for display.

    Accepts both the legacy dict format and WorkerTask objects.

    Args:
        result: Result dict or WorkerTask from SubagentCoordinator.

    Returns:
        Human-readable formatted string.
    """
    if isinstance(result, WorkerTask):
        sub_id = result.worker_id
        status = result.status.value
        duration = result.duration_seconds
        error = result.error
        output = result.output or ""
    else:
        sub_id = result.get("sub_id", "unknown")
        status = result.get("status", "unknown")
        duration = result.get("duration_seconds", 0)
        error = result.get("error")
        output = result.get("output", "")

    lines = ["<subagent_result>"]
    lines.append(f"## {sub_id} ({status}) [{duration:.1f}s]")

    if error:
        lines.append(f"Error: {error}")
    elif output:
        # Truncate long output
        if len(output) > 1000:
            output = output[:1000] + "\n... (truncated)"
        lines.append(f"Output:\n{output}")

    lines.append("</subagent_result>")
    return "\n".join(lines)
