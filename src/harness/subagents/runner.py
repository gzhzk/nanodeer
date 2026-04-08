"""Subagent runner - lightweight async execution."""

import asyncio
import uuid
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import BaseTool


async def run_subagent(
    subagent_id: str,
    name: str,
    task: str,
    tools: list[BaseTool],
    llm: BaseChatModel,
    timeout: int = 900,
) -> dict[str, Any]:
    """Run a subagent task asynchronously.

    Simplified implementation using asyncio for parallel execution.
    No complex thread pool or lifecycle management.

    Args:
        subagent_id: Unique identifier for this subagent.
        name: Subagent name (e.g., "researcher", "coder").
        task: Task description.
        tools: List of tools available to this subagent.
        llm: LLM to use for this subagent.
        timeout: Timeout in seconds (default 15 minutes).

    Returns:
        Dict with subagent_id, status, output, artifacts, error.
    """
    import time
    start_time = time.time()

    try:
        # Bind tools to LLM
        llm_with_tools = llm.bind_tools(tools) if tools else llm

        # Build system prompt for subagent
        system_prompt = f"""You are {name}, a specialized subagent.

Your task: {task}

Guidelines:
- Complete the task thoroughly
- Use tools when needed
- Report your findings in clear, structured format
- If you encounter errors, explain what happened and what you tried
"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Please complete this task: {task}"),
        ]

        # Simple ReAct loop
        max_iterations = 10
        for _ in range(max_iterations):
            response = await llm_with_tools.ainvoke(messages)

            if not hasattr(response, "tool_calls") or not response.tool_calls:
                # No tool calls - we're done
                duration = time.time() - start_time
                return {
                    "subagent_id": subagent_id,
                    "name": name,
                    "status": "completed",
                    "output": response.content if hasattr(response, "content") else str(response),
                    "artifacts": [],
                    "error": None,
                    "duration_seconds": duration,
                }

            # Execute tool calls
            tool_results = []
            for tc in response.tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]

                # Find the tool
                tool = next((t for t in tools if t.name == tool_name), None)
                if not tool:
                    tool_results.append(f"Tool {tool_name} not found")
                    continue

                try:
                    result = await tool.ainvoke(tool_args)
                    tool_results.append(str(result))
                except Exception as e:
                    tool_results.append(f"Error: {str(e)}")

            # Add response and tool results to messages
            messages.append(response)
            for i, tc in enumerate(response.tool_calls):
                result_content = tool_results[i] if i < len(tool_results) else "No result"
                messages.append(ToolMessage(
                    tool_call_id=tc["id"],
                    name=tc["name"],
                    content=result_content,
                ))

        # Max iterations reached
        duration = time.time() - start_time
        return {
            "subagent_id": subagent_id,
            "name": name,
            "status": "failed",
            "output": "Max iterations reached",
            "artifacts": [],
            "error": "Max iterations reached",
            "duration_seconds": duration,
        }

    except asyncio.TimeoutError:
        duration = time.time() - start_time
        return {
            "subagent_id": subagent_id,
            "name": name,
            "status": "timeout",
            "output": "",
            "artifacts": [],
            "error": f"Task timed out after {timeout} seconds",
            "duration_seconds": duration,
        }
    except Exception as e:
        duration = time.time() - start_time
        return {
            "subagent_id": subagent_id,
            "name": name,
            "status": "failed",
            "output": "",
            "artifacts": [],
            "error": str(e),
            "duration_seconds": duration,
        }


async def run_subagents_in_parallel(
    subagent_specs: list[dict[str, Any]],
    llm: BaseChatModel,
    timeout: int = 900,
) -> list[dict[str, Any]]:
    """Run multiple subagents in parallel using asyncio.gather.

    Args:
        subagent_specs: List of dicts with keys: subagent_id, name, task, tools
        llm: LLM to use for all subagents
        timeout: Timeout per subagent in seconds

    Returns:
        List of result dicts
    """
    tasks = []
    for spec in subagent_specs:
        task = asyncio.create_task(
            run_subagent(
                subagent_id=spec["subagent_id"],
                name=spec["name"],
                task=spec["task"],
                tools=spec.get("tools", []),
                llm=llm,
                timeout=timeout,
            )
        )
        tasks.append(task)

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Convert exceptions to error dicts
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append({
                "subagent_id": subagent_specs[i]["subagent_id"],
                "name": subagent_specs[i]["name"],
                "status": "failed",
                "output": "",
                "artifacts": [],
                "error": str(result),
                "duration_seconds": 0,
            })
        else:
            processed_results.append(result)

    return processed_results


def generate_subagent_id() -> str:
    """Generate a unique subagent ID."""
    return f"subagent-{uuid.uuid4().hex[:8]}"
