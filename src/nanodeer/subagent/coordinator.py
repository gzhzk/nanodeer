"""SubagentCoordinator — manages worker lifecycle, replaces module-level globals."""

import asyncio
import logging
import time
from collections import deque

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import BaseTool

from nanodeer.agent.messages import ToolMessage
from nanodeer.sandbox import set_sandbox, clear_sandbox

from .types import WorkerStatus, WorkerTask, WorkerSpec

logger = logging.getLogger(__name__)


class SubagentCoordinator:
    """Manages subagent worker lifecycle with semaphore-based concurrency control.

    Replaces module-level global _executor pattern. Provides spawn, get_result,
    stop, and list methods for full lifecycle management.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool],
        sandbox_provider,
        max_concurrent: int = 3,
        timeout_seconds: int = 900,
        tool_schemas: list[BaseTool] | None = None,
    ):
        self.llm = llm
        self.tools = tools
        self.tool_schemas = tool_schemas or tools
        self.sandbox_provider = sandbox_provider
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._timeout_seconds = timeout_seconds
        self._pending: deque[WorkerTask] = deque()
        self._active: dict[str, WorkerTask] = {}
        self._completed: dict[str, WorkerTask] = {}
        self._lock = asyncio.Lock()

    def _find_tool(self, name: str) -> BaseTool | None:
        return next((t for t in self.tools if t.name == name), None)

    def get_result(self, worker_id: str) -> WorkerTask | None:
        """Get completed worker task by ID."""
        return self._completed.get(worker_id)

    def stop(self, worker_id: str) -> bool:
        """Cancel a pending or running worker.

        Returns True if worker was found and action taken, False otherwise.
        """
        if worker_id in self._pending_ids:
            self._pending = deque(w for w in self._pending if w.worker_id != worker_id)
            task = WorkerTask(worker_id=worker_id, name="cancelled", status=WorkerStatus.CANCELLED)
            self._completed[worker_id] = task
            return True
        if worker_id in self._active:
            self._active[worker_id].status = WorkerStatus.CANCELLED
            return True
        return False

    def list_pending(self) -> list[WorkerTask]:
        return list(self._pending)

    def list_active(self) -> list[WorkerTask]:
        return list(self._active.values())

    def list_completed(self) -> list[WorkerTask]:
        return list(self._completed.values())

    @property
    def _pending_ids(self) -> set[str]:
        return {w.worker_id for w in self._pending}

    def spawn(self, task: str, name: str = "worker", spec: WorkerSpec | None = None) -> str:
        """Create a worker task and schedule it for execution.

        Returns the worker_id immediately; execution happens in background.
        """
        worker = WorkerTask(
            name=name,
            task=task,
            status=WorkerStatus.PENDING,
            created_at=time.time(),
            spec=spec or WorkerSpec(
                timeout_seconds=self._timeout_seconds,
            ),
        )
        self._pending.append(worker)
        asyncio.create_task(self._schedule(worker))
        task_preview = task[:100] + "..." if len(task) > 100 else task
        logger.info("spawn worker_id=%s name=%s pending=%d task=%s",
                    worker.worker_id, name, len(self._pending), task_preview)
        return worker.worker_id

    async def _schedule(self, worker: WorkerTask) -> None:
        """Wait for semaphore, then run the worker."""
        spec = worker.spec or WorkerSpec(timeout_seconds=self._timeout_seconds)
        try:
            async with self._semaphore:
                worker.status = WorkerStatus.RUNNING
                worker.started_at = time.time()
                self._active[worker.worker_id] = worker

                result = await self._run_worker(worker, spec)

                worker.status = result.status
                worker.output = result.output
                worker.error = result.error
                worker.completed_at = time.time()
                worker.duration_seconds = (worker.completed_at - worker.started_at)

                self._completed[worker.worker_id] = worker
                self._active.pop(worker.worker_id, None)
                logger.info("done worker_id=%s name=%s status=%s duration=%.2fs",
                            worker.worker_id, worker.name, worker.status.value,
                            worker.duration_seconds)

        except asyncio.CancelledError:
            worker.status = WorkerStatus.CANCELLED
            worker.completed_at = time.time()
            worker.duration_seconds = (worker.completed_at - (worker.started_at or worker.completed_at))
            self._completed[worker.worker_id] = worker
            self._active.pop(worker.worker_id, None)
            logger.info("done worker_id=%s name=%s status=%s duration=%.2fs",
                        worker.worker_id, worker.name, worker.status.value,
                        worker.duration_seconds)

    def _format_result_dict(self, worker: WorkerTask) -> dict:
        """Backward-compatible result dict for format_result()."""
        return {
            "sub_id": worker.worker_id,
            "status": worker.status.value,
            "output": worker.output or "",
            "error": worker.error,
            "duration_seconds": worker.duration_seconds,
        }

    async def run(self, task: str, sub_id: str | None = None) -> dict:
        """Legacy compatibility: run a single task synchronously (awaits completion).

        Used by run_many and direct callers. Returns a result dict for backward
        compatibility with format_result().
        """
        worker = WorkerTask(
            worker_id=sub_id or f"sub-{uuid_hex()}",
            name="worker",
            task=task,
            status=WorkerStatus.PENDING,
            created_at=time.time(),
            spec=WorkerSpec(timeout_seconds=self._timeout_seconds),
        )
        async with self._semaphore:
            result = await self._run_worker(worker, worker.spec)
            self._completed[worker.worker_id] = result
        return self._format_result_dict(result)

    async def _run_worker(self, worker: WorkerTask, spec: WorkerSpec) -> WorkerTask:
        """Execute worker task: sandbox → ReAct loop → release."""
        sandbox = None
        try:
            sandbox = await self.sandbox_provider.acquire(worker.worker_id)
            set_sandbox(worker.worker_id, sandbox)

            messages = [
                SystemMessage(content=f"You are a helpful assistant.\n\nTask: {worker.task}"),
                HumanMessage(content=worker.task),
            ]
            llm_bound = self.llm.bind_tools(self.tool_schemas)

            for _ in range(spec.max_iterations):
                response = await llm_bound.ainvoke(messages)
                raw_tcs = getattr(response, "tool_calls", None) or []

                if not raw_tcs:
                    worker.output = response.content if hasattr(response, "content") else str(response)
                    worker.status = WorkerStatus.COMPLETED
                    return worker

                for tc in raw_tcs:
                    tool = self._find_tool(tc["name"])
                    if tool is None:
                        messages.append(ToolMessage(
                            content=f"Tool {tc['name']} not found",
                            tool_call_id=tc.get("id", ""),
                            name=tc["name"],
                        ))
                        continue
                    try:
                        result = await tool.ainvoke(tc.get("args", {}), exec_id=worker.worker_id)
                        messages.append(ToolMessage(
                            content=str(result),
                            tool_call_id=tc.get("id", ""),
                            name=tc["name"],
                        ))
                    except Exception as e:
                        messages.append(ToolMessage(
                            content=f"Error: {e}",
                            tool_call_id=tc.get("id", ""),
                            name=tc["name"],
                        ))

            worker.status = WorkerStatus.FAILED
            worker.error = "Max iterations reached"
            return worker

        except asyncio.TimeoutError:
            worker.status = WorkerStatus.TIMEOUT
            worker.error = "Task timed out"
            return worker

        except Exception as e:
            worker.status = WorkerStatus.FAILED
            worker.error = str(e)
            return worker

        finally:
            if sandbox:
                try:
                    await self.sandbox_provider.release(sandbox)
                except Exception:
                    pass
                clear_sandbox(worker.worker_id)


def uuid_hex() -> str:
    """Generate a short hex ID."""
    import uuid as _uuid
    return f"sub-{_uuid.uuid4().hex[:8]}"
