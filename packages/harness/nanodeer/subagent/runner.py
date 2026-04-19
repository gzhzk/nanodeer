"""Subagent executor - lightweight parallel task execution."""

import asyncio
import uuid
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import BaseTool

from nanodeer.agent.messages import ToolMessage
from nanodeer.sandbox import set_sandbox, clear_sandbox


class SubagentExecutor:
    """Lightweight parallel task executor.

    Each subagent runs in its own sandbox context (exec_id),
    reusing the same tools and sandbox provider as the main agent.
    """

    MAX_CONCURRENT = 3
    MAX_ITERATIONS = 10

    def __init__(self, llm: BaseChatModel, tools: list[BaseTool], sandbox_provider):
        """Initialize executor.

        Args:
            llm: Chat model for subagent reasoning.
            tools: List of tools available to subagents.
            sandbox_provider: SandboxProvider instance for execution isolation.
        """
        self.llm = llm
        self.tools = tools
        self.sandbox_provider = sandbox_provider
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)
        self._results: dict[str, dict[str, Any]] = {}

    def _find_tool(self, name: str) -> BaseTool | None:
        """Find tool by name."""
        return next((t for t in self.tools if t.name == name), None)

    async def run(self, task: str, sub_id: str | None = None) -> dict[str, Any]:
        """Execute a single subagent task.

        Args:
            task: Task description for the subagent.
            sub_id: Optional subagent ID. Generated if not provided.

        Returns:
            Dict with sub_id, status, output, error, duration_seconds.
        """
        import time

        sub_id = sub_id or f"sub-{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        async with self._semaphore:
            sandbox = await self.sandbox_provider.acquire(sub_id)
            set_sandbox(sub_id, sandbox)

            try:
                messages = [
                    SystemMessage(content=f"你是一个专业助手。\n\n任务：{task}"),
                    HumanMessage(content=task),
                ]

                for _ in range(self.MAX_ITERATIONS):
                    response = await self.llm.bind_tools(self.tools).ainvoke(messages)

                    if not hasattr(response, "tool_calls") or not response.tool_calls:
                        duration = time.time() - start_time
                        result = {
                            "sub_id": sub_id,
                            "status": "completed",
                            "output": response.content if hasattr(response, "content") else str(response),
                            "error": None,
                            "duration_seconds": duration,
                        }
                        self._results[sub_id] = result
                        return result

                    # Execute tool calls
                    for tc in response.tool_calls:
                        tool_name = tc["name"]
                        tool_args = tc.get("args", {})

                        tool = self._find_tool(tool_name)
                        if tool is None:
                            messages.append(ToolMessage(
                                content=f"Tool {tool_name} not found",
                                tool_call_id=tc.get("id", ""),
                                name=tool_name,
                            ))
                            continue

                        try:
                            # Route to sandbox via exec_id
                            tool_result = await tool.ainvoke(tool_args, exec_id=sub_id)
                            messages.append(ToolMessage(
                                content=str(tool_result),
                                tool_call_id=tc.get("id", ""),
                                name=tool_name,
                            ))
                        except Exception as e:
                            messages.append(ToolMessage(
                                content=f"Error: {str(e)}",
                                tool_call_id=tc.get("id", ""),
                                name=tool_name,
                            ))

                # Max iterations reached
                duration = time.time() - start_time
                result = {
                    "sub_id": sub_id,
                    "status": "max_iterations",
                    "output": "",
                    "error": "Max iterations reached",
                    "duration_seconds": duration,
                }
                self._results[sub_id] = result
                return result

            except asyncio.TimeoutError:
                duration = time.time() - start_time
                result = {
                    "sub_id": sub_id,
                    "status": "timeout",
                    "output": "",
                    "error": "Task timed out",
                    "duration_seconds": duration,
                }
                self._results[sub_id] = result
                return result

            except Exception as e:
                duration = time.time() - start_time
                result = {
                    "sub_id": sub_id,
                    "status": "error",
                    "output": "",
                    "error": str(e),
                    "duration_seconds": duration,
                }
                self._results[sub_id] = result
                return result

            finally:
                await self.sandbox_provider.release(sandbox)
                clear_sandbox(sub_id)

    def get_result(self, sub_id: str) -> dict[str, Any] | None:
        """Get result of a completed subagent.

        Args:
            sub_id: The subagent ID.

        Returns:
            Result dict if completed, None if still running or not found.
        """
        return self._results.get(sub_id)


async def run_many(tasks: list[dict[str, Any]], executor: SubagentExecutor) -> list[dict[str, Any]]:
    """Run multiple subagent tasks in parallel.

    Args:
        tasks: List of dicts with "task" (required) and "sub_id" (optional).
        executor: SubagentExecutor instance.

    Returns:
        List of result dicts.
    """
    coros = [
        executor.run(t["task"], t.get("sub_id"))
        for t in tasks
    ]

    results = await asyncio.gather(*coros, return_exceptions=True)

    # Process exceptions into result dicts
    processed = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            processed.append({
                "sub_id": tasks[i].get("sub_id", f"unknown-{i}"),
                "status": "error",
                "output": "",
                "error": str(r),
                "duration_seconds": 0,
            })
        else:
            processed.append(r)

    return processed


def format_result(result: dict[str, Any]) -> str:
    """Format a subagent result for display.

    Args:
        result: Result dict from SubagentExecutor.

    Returns:
        Human-readable formatted string.
    """
    sub_id = result.get("sub_id", "unknown")
    status = result.get("status", "unknown")
    duration = result.get("duration_seconds", 0)
    error = result.get("error")
    output = result.get("output", "")

    lines = [f"<subagent_result>"]
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
