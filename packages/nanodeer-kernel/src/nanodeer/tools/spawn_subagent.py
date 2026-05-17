"""Subagent tools - spawn and retrieve subagent results."""

from langchain_core.tools import tool

from ..subagent import get_executor, format_result


@tool
async def spawn_subagent(
    task: str,
    name: str = "worker",
) -> str:
    """Spawn a subagent to execute a task in parallel with the main agent.

    The subagent runs in the background. Use get_subagent_results
    to retrieve the result after the subagent completes.

    Args:
        task: Detailed description of what this subagent should do.
        name: Subagent name/role (e.g., "researcher", "coder", "writer").

    Returns:
        A message with the subagent ID. Use get_subagent_results(sub_id) to get results.
    """
    coordinator = get_executor()
    worker_id = coordinator.spawn(task, name=name)

    return f"Subagent {name} started: {worker_id}"


@tool
async def get_subagent_results(sub_id: str) -> str:
    """Get the result of a previously spawned subagent.

    Call this after spawn_subagent returns to get the execution results.

    Args:
        sub_id: The subagent ID returned by spawn_subagent.

    Returns:
        Formatted subagent results (status, output, error, duration).
    """
    coordinator = get_executor()
    result = coordinator.get_result(sub_id)

    if result is None:
        return f"Subagent {sub_id} is still running or not found."

    return format_result(result)
