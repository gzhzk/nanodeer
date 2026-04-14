"""Subagent tools - direct SubagentRunner integration."""

from typing import Optional

from langchain_core.tools import tool

from ..subagents import generate_subagent_id, get_runner


@tool
async def spawn_subagent(
    name: str,
    task: str,
    subagent_type: str = "general",
    thread_id: Optional[str] = None,
) -> str:
    """Spawn a subagent to execute a task and return its results.

    Use this when a task can be broken into independent parts that run simultaneously.

    Args:
        name: Subagent name/role (e.g., "researcher", "coder", "writer").
        task: Detailed description of what this subagent should do.
        subagent_type: Type of subagent capabilities:
            - "general": Full-featured, can use all tools
            - "bash": Bash-only
        thread_id: Thread identifier for multi-threaded environments.

    Returns:
        Formatted summary of subagent results (status, output, duration).
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
    # Execute and return results in one call
    return await runner.get_results(thread_id or "default")
