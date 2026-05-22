"""NanoDeer Brain — NDJSON stdio protocol adapter.

This is Layer 5 (Protocol Adapter) in the NanoDeer architecture.
It reads ExecuteRequest from stdin, calls NanoEngine.run_streaming(),
and streams events to stdout.

Usage:
    python -m nanodeer.brain --stdio

Protocol:
    stdin:  {"type":"execute","prompt":"...","threadId":"..."}
    stdout: {"event":"start",...}
    stdout: {"event":"llm_token",...}
    stdout: {"event":"tool_call",...}
    stdout: {"event":"tool_result",...}
    stdout: {"event":"end",...}
    stderr: logs (not NDJSON)
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import AsyncGenerator

# Load .env from project root if exists
# __file__ = nanodeer/cli/brain.py
# parents: brain.py -> cli -> nanodeer -> root
_env = Path(__file__).resolve().parents[3] / ".env"
if _env.exists():
    from dotenv import load_dotenv
    load_dotenv(_env)

logger = logging.getLogger(__name__)


class Brain:
    """NDJSON over stdio interface for NanoDeer Kernel."""

    def __init__(self):
        from nanodeer.config import get_config
        from nanodeer.engine import NanoEngine

        self.config = get_config()
        self.engine = NanoEngine(self.config)
        self._running_tasks: dict[str, asyncio.Task] = {}

    async def execute_stream(
        self,
        prompt: str,
        thread_id: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Execute a prompt and yield stream events."""
        async for event in self.engine.run_streaming(
            prompt=prompt,
            thread_id=thread_id,
        ):
            yield event

    def cancel(self, thread_id: str) -> bool:
        """Cancel a running task."""
        if thread_id in self._running_tasks:
            self._running_tasks[thread_id].cancel()
            del self._running_tasks[thread_id]
            return True
        return False


async def read_stdin() -> AsyncGenerator[dict, None]:
    """Read NDJSON lines from stdin."""
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break
        decoded = line.decode().strip()
        if decoded:
            try:
                yield json.loads(decoded)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON: {decoded}")


async def handle_request(brain: Brain, request: dict) -> AsyncGenerator[dict, None]:
    """Handle a single request and yield response events."""
    req_type = request.get("type", "")

    if req_type == "execute":
        prompt = request.get("prompt", "")
        thread_id = request.get("threadId")

        queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=64)

        async def producer():
            try:
                async for event in brain.execute_stream(prompt, thread_id):
                    await queue.put(event)
            finally:
                await queue.put(None)

        task = asyncio.create_task(producer())
        if thread_id:
            brain._running_tasks[thread_id] = task

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            brain._running_tasks.pop(thread_id, None)
            if not task.done():
                task.cancel()

    elif req_type == "cancel":
        thread_id = request.get("threadId")
        brain.cancel(thread_id)
        yield {"event": "cancelled", "threadId": thread_id}

    elif req_type == "ping":
        yield {"event": "pong"}

    else:
        logger.warning(f"Unknown request type: {req_type}")
        yield {"event": "error", "code": "UNKNOWN_REQUEST", "message": f"Unknown type: {req_type}"}


async def main():
    """Main stdio loop."""
    brain = Brain()

    async for request in read_stdin():
        async for event in handle_request(brain, request):
            print(json.dumps(event), flush=True)


def main_wrapper():
    """Sync wrapper for entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="[NanoDeer] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    asyncio.run(main())


if __name__ == "__main__":
    main_wrapper()
