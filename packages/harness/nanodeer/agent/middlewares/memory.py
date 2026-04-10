"""Memory middleware for L2/L3 tiered memory management.

Loads memory context before agent starts.
Saves episodic session logs and triggers distillation after agent ends.
"""

from typing import TYPE_CHECKING, Any, Optional

from .base import Middleware

if TYPE_CHECKING:
    from ..memory.storage import MemoryStore
    from ..memory.extractor import MemoryExtractor


class MemoryMiddleware(Middleware):
    """Manages L2/L3 tiered memory.

    before_agent_start: Loads L3 (MEMORY.md) + recent episodic into state.memory_context.
    after_agent_end: Writes episodic session log + checks for distillation.
    """

    def __init__(
        self,
        memory_store: "MemoryStore",
        extractor: Optional["MemoryExtractor"] = None,
        auto_extract: bool = True,
    ):
        """Initialize MemoryMiddleware.

        Args:
            memory_store: MemoryStore instance.
            extractor: MemoryExtractor for distillation. Optional.
            auto_extract: Whether to write episodic and distill. Default True.
        """
        self.store = memory_store
        self.extractor = extractor
        self.auto_extract = auto_extract

    async def before_agent_start(self, state: Any) -> None:
        """Load memory context into state.

        Combines L3 (MEMORY.md) + recent episodic (today + yesterday).
        """
        # Load combined L3 + recent episodic
        memory_context = self.store.load()

        # Load project memory if available
        project_slug = getattr(state, "project_slug", None) or "default"
        project_mem = self.store.load_project_memory(project_slug)
        if project_mem:
            sep = "\n\n" if memory_context else ""
            memory_context = memory_context + sep + f"<project_memory>\n{project_mem}\n</project_memory>"

        if isinstance(state, dict):
            state["memory_context"] = memory_context
        else:
            state.memory_context = memory_context  # type: ignore

    async def after_agent_end(self, state: Any) -> None:
        """Write episodic log and check for distillation."""
        if not self.auto_extract:
            return

        # Build episodic entry from this session
        from datetime import date
        from ..memory.types import EpisodicEntry

        messages = getattr(state, "messages", []) if not isinstance(state, dict) else state.get("messages", [])
        if not messages:
            return

        # Extract key info from messages for episodic
        summary = self._summarize_session(messages)
        episodic_entry = EpisodicEntry(
            date=date.today().isoformat(),
            turn=1,
            role="session",
            content=summary,
        )

        self.store.save_episodic(episodic_entry.to_markdown())

        # Check for distillation trigger
        if self.extractor and self.store.should_distill():
            await self._distill()

    def _summarize_session(self, messages: list) -> str:
        """Extract a brief summary of the session for episodic log."""
        user_msgs = []
        agent_msgs = []

        for msg in messages:
            cls_name = type(msg).__name__
            content = getattr(msg, "content", "") or ""
            if len(content) > 500:
                content = content[:500] + "..."
            if cls_name == "HumanMessage":
                user_msgs.append(content)
            elif cls_name == "AIMessage":
                agent_msgs.append(content)

        lines = []
        if user_msgs:
            lines.append(f"User request: {user_msgs[0]}")
        if agent_msgs:
            lines.append(f"Agent response: {agent_msgs[0][:300]}")
        return "\n".join(lines) if lines else "(empty session)"

    async def _distill(self) -> None:
        """Distill episodic files into MEMORY.md."""
        if not self.extractor:
            return

        episodic_files = self.store.list_episodic()
        if len(episodic_files) < 3:
            return

        # Load all episodic content
        parts = []
        for d in episodic_files[-10:]:  # Last 10 episodic files
            content = self.store.load_episodic(d)
            if content:
                parts.append(f"## {d.isoformat()}\n\n{content}")

        if not parts:
            return

        combined = "\n\n---\n\n".join(parts)
        distilled = await self.extractor.distill(combined)

        if distilled:
            self.store.save_memory(distilled, name="distilled-memory", description="Auto-distilled from episodic logs")

    async def after_tool_call(
        self, state: Any, tool_name: str, tool_args: dict, result: str
    ) -> str:
        """Intercept save_memory tool calls."""
        if tool_name != "save_memory":
            return result

        content = tool_args.get("content", "")
        if not content:
            return result

        # Determine if this is user or project memory
        category = tool_args.get("category", "user")
        project = tool_args.get("project", None)

        if project:
            self.store.save_project_memory(project, content)
        else:
            self.store.save_memory(content)

        return result
