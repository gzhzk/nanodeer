"""MemoryMiddleware — loads memory context into signals, handles memory writes on host.

before_llm_streaming:
  - Loads USER.md + wiki entries (context-aware) + MEMORY.md + episodic
  - Passes last user message as context_hint for wiki retrieval
  - Injects memory_context into signals for prompt assembly

before_tools_streaming:
  - Intercepts save_memory/save_user_memory and writes directly on host.
    These tools MUST run on the host, not inside the sandbox, because
    MemoryStore writes to ~/.nanodeer/memory/ which is not mounted into containers.
  - Routes wiki/ targets to WikiStore, others to legacy MEMORY.md/USER.md
"""

from nanodeer.agent.memory.storage import MemoryStore
from nanodeer.agent.messages import HumanMessage
from nanodeer.agent.state import ThreadState, TurnSignals

from .base import Middleware

_MEMORY_TOOL_NAMES = {"save_memory", "save_user_memory"}
_UNSET = object()  # sentinel to distinguish "no arg" from "explicit None"


class MemoryMiddleware(Middleware):
    """Loads memory into state before LLM call; handles memory writes on host."""

    def __init__(self, memory_store=_UNSET):
        self._memory_store = MemoryStore() if memory_store is _UNSET else memory_store

    @staticmethod
    def _get_last_user_message(messages) -> str:
        """Extract the last user message from conversation history."""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                content = msg.content
                return content if isinstance(content, str) else str(content or "")
        return ""

    async def before_llm_streaming(self, state: ThreadState, signals: TurnSignals):
        if not self._memory_store:
            return
        yield  # make it an async generator

        # Use last user message as context hint for wiki retrieval
        context_hint = self._get_last_user_message(state.messages) or None
        memory_context = self._memory_store.load_for_prompt(context_hint=context_hint)

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
            target = tool_args.get("target", "memory")
            content = tool_args.get("content", "")
            tags = tool_args.get("tags", None)

            if target.startswith("wiki/"):
                path = target.removeprefix("wiki/").strip("/")
                if path:
                    self._memory_store.save_wiki_entry(path, content, tags=tags)
                    tag_info = f" tags=[{', '.join(tags)}]" if tags else ""
                    preview = content[:200] + "..." if len(content) > 200 else content
                    signals.skip_tool_result = f"Wiki entry saved [{path}]:{tag_info} {preview}"
                else:
                    signals.skip_tool_result = "Error: wiki path must not be empty"
            elif target == "user":
                self._memory_store.save_user_memory(content)
                preview = content[:200] + "..." if len(content) > 200 else content
                signals.skip_tool_result = f"User memory saved: {preview}"
            else:
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
