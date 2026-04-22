"""MemoryMiddleware — loads memory context into signals, handles memory writes on host.

before_llm_streaming:
  - Loads USER + MEMORY + episodic from MemoryStore
  - Appends uploaded file summaries → signals.memory_context

before_tools_streaming:
  - Intercepts save_memory/save_user_memory and writes directly on host.
    These tools MUST run on the host, not inside the sandbox, because
    MemoryStore writes to ~/.nanodeer/memory/ which is not mounted into containers.
"""

from nanodeer.agent.memory.storage import MemoryStore
from nanodeer.agent.state import ThreadState, TurnSignals

from .base import Middleware

_MEMORY_TOOL_NAMES = {"save_memory", "save_user_memory"}


class MemoryMiddleware(Middleware):
    """Loads memory into state before LLM call; handles memory writes on host."""

    def __init__(self, memory_store=None):
        self._memory_store = memory_store or MemoryStore()

    async def before_llm_streaming(self, state: ThreadState, signals: TurnSignals):
        if not self._memory_store:
            return
        yield  # make it an async generator

        memory_context = self._memory_store.load_for_prompt()

        if memory_context:
            signals.memory_context = memory_context
            signals.events.append({
                "type": "memory_context",
                "has_memory": True,
            })
        else:
            signals.events.append({
                "type": "memory_context",
                "has_memory": False,
            })

    async def before_tools_streaming(
        self, state: ThreadState, signals: TurnSignals, tool_name: str, tool_args: dict
    ):
        """Intercept memory tools and write directly on host, bypassing sandbox."""
        if tool_name not in _MEMORY_TOOL_NAMES:
            return
        if not self._memory_store:
            return
        yield  # make it an async generator

        if tool_name == "save_memory":
            content = tool_args.get("content", "")
            mode = tool_args.get("mode", "append")
            self._memory_store.save_memory(content, mode=mode)
            preview = content[:200] + "..." if len(content) > 200 else content
            signals.skip_tool_result = f"Memory {'replaced' if mode == 'replace' else 'saved'}: {preview}"
        elif tool_name == "save_user_memory":
            content = tool_args.get("content", "")
            self._memory_store.save_user_memory(content)
            preview = content[:200] + "..." if len(content) > 200 else content
            signals.skip_tool_result = f"User memory saved: {preview}"

        signals.skip_tool = True
