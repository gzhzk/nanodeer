"""Subagent tools - spawn and manage parallel subagents."""

from langchain_core.tools import tool

from ..subagents import generate_subagent_id


@tool
def spawn_subagent(
    name: str,
    task: str,
    subagent_type: str = "general",
) -> str:
    """Spawn a subagent to execute a task in parallel with other subagents.

    Use this when a task can be broken into independent parts that run simultaneously.
    The main agent will continue and can use get_subagent_results() to collect outputs.

    Args:
        name: Subagent name/role (e.g., "researcher", "coder", "writer").
              This identifies what kind of work this subagent does.
        task: Detailed description of what this subagent should do.
              Be specific about inputs, expected outputs, and any constraints.
        subagent_type: Type of subagent capabilities:
            - "general": Full-featured, can use all tools (ReadFile, WriteFile, Bash, etc.)
            - "bash": Bash-only, can only execute shell commands

    Returns:
        A subagent_id in format "subagent-xxxxxxxx".
        Store this ID to reference the subagent's results later.
    """
    subagent_id = generate_subagent_id()
    # Note: Actual spawning happens asynchronously via SubagentMiddleware
    # This tool just registers the intent in state
    return f"Subagent spawned: {subagent_id}\nName: {name}\nTask: {task}\nType: {subagent_type}\n\nUse get_subagent_results() to collect results after completion."


@tool
def get_subagent_results() -> str:
    """Get results from all completed subagents.

    Returns a formatted summary of all subagent results including:
    - subagent_id and name
    - status (completed/failed/timeout)
    - output content
    - any errors

    Note: The SubagentMiddleware will replace the placeholder with actual results.
    """
    # Placeholder - middleware replaces this with actual results
    return "[SUBAGENT_RESULTS_PLACEHOLDER]"


def format_subagent_results(results: list[dict]) -> str:
    """Format subagent results for display."""
    if not results:
        return "(no subagent results yet)"

    lines = ["=== Subagent Results ==="]
    for r in results:
        lines.append(f"\n## {r.get('name', 'subagent')} ({r.get('status', 'unknown')})")
        lines.append(f"ID: {r.get('subagent_id', 'unknown')}")
        output = r.get('output', '')
        if output:
            lines.append(f"Output:\n{output[:500]}..." if len(output) > 500 else f"Output:\n{output}")
        if r.get('error'):
            lines.append(f"Error: {r.get('error')}")
        lines.append(f"Duration: {r.get('duration_seconds', 0):.1f}s")

    return "\n".join(lines)
