"""Subagent tools - direct SubagentRunner integration."""

from typing import Optional

from langchain_core.tools import tool

from ..subagents import generate_subagent_id, get_runner


@tool
def spawn_subagent(
    name: str,
    task: str,
    subagent_type: str = "general",
    thread_id: Optional[str] = None,
) -> str:
    """Spawn a subagent to execute a task in parallel with other subagents.

    Use this when a task can be broken into independent parts that run simultaneously.
    Call get_subagent_results() to collect outputs after spawning.

    Args:
        name: Subagent name/role (e.g., "researcher", "coder", "writer").
        task: Detailed description of what this subagent should do.
        subagent_type: Type of subagent capabilities:
            - "general": Full-featured, can use all tools
            - "bash": Bash-only

    Returns:
        A subagent_id in format "subagent-xxxxxxxx".
    """
    runner = get_runner()
    subagent_id = generate_subagent_id()
    runner.collect_spawn(
        subagent_id=subagent_id,
        name=name,
        task=task,
        subagent_type=subagent_type,
        thread_id=thread_id or "default",
    )
    return f"Subagent spawned: {subagent_id}\nName: {name}\nTask: {task}\n\nUse get_subagent_results() to collect results."


@tool
async def get_subagent_results(thread_id: Optional[str] = None) -> str:
    """Get results from all completed subagents.

    Executes any pending subagents first, then returns formatted results.

    Args:
        thread_id: Thread identifier for multi-threaded environments.

    Returns:
        Formatted summary of all subagent results.
    """
    runner = get_runner()
    return await runner.get_results(thread_id or "default")
