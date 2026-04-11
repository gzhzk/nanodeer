"""MemoryMiddleware — L2/L3 tiered memory management.

before_llm: loads memory context into state.metadata["memory_context"].
after_tools: intercepts save_memory tool calls and persists to storage.
"""

from typing import TYPE_CHECKING, Any, Optional

from .base import Middleware

if TYPE_CHECKING:
    from ..state import ThreadState
    from ..memory.storage import MemoryStore
    from ..memory.extractor import MemoryExtractor


class MemoryMiddleware(Middleware):
    """Manages L2/L3 tiered memory.

    before_llm: Loads L3 (MEMORY.md) + recent episodic into metadata["memory_context"].
    after_tools: Intercepts save_memory tool calls and persists to storage.
    """

    def __init__(
        self,
        memory_store: "MemoryStore",
        extractor: Optional["MemoryExtractor"] = None,
        auto_extract: bool = True,
    ):
        self.store = memory_store
        self.extractor = extractor
        self.auto_extract = auto_extract

    async def before_llm(self, state: "ThreadState") -> None:
        """Load memory context into state.metadata."""
        memory_context = self.store.load()

        project_slug = getattr(state, "project_slug", None) or "default"
        project_mem = self.store.load_project_memory(project_slug)
        if project_mem:
            sep = "\n\n" if memory_context else ""
            memory_context = memory_context + sep + f"<project_memory>\n{project_mem}\n</project_memory>"

        state.metadata["memory_context"] = memory_context

    async def after_tools(
        self, state: "ThreadState", tool_name: str, tool_args: dict, result: str
    ) -> str:
        """Intercept save_memory tool calls."""
        if tool_name != "save_memory":
            return result

        content = tool_args.get("content", "")
        if not content:
            return result

        category = tool_args.get("category", "user")
        project = tool_args.get("project", None)

        if project:
            self.store.save_project_memory(project, content)
        else:
            self.store.save_memory(content)

        return result