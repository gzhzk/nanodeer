"""Memory middleware for loading memory context before agent starts."""

from typing import TYPE_CHECKING, Optional

from .base import Middleware

if TYPE_CHECKING:
    from ..memory.storage import MemoryStore


class MemoryMiddleware(Middleware):
    """Loads memory context into ThreadState before agent starts.

    v1 focuses on read-only: loads user + project memory from file storage
    and injects it into state.memory_context. The builder reads this field
    when constructing the system prompt.

    Storage: ~/.nanodeer/memory/{user_id}/
    """

    def __init__(
        self,
        memory_store: "MemoryStore",
        project_slug: str = "default",
    ):
        """Initialize MemoryMiddleware.

        Args:
            memory_store: MemoryStore instance for reading memory files.
            project_slug: Project identifier for project-specific memory.
                         Defaults to "default".
        """
        self.memory_store = memory_store
        self.project_slug = project_slug

    async def before_agent_start(self, state: "ThreadState") -> None:
        """Load memory context into state.

        Reads user and project memory from file storage and stores the
        combined context in state.memory_context for prompt injection.

        Args:
            state: Current ThreadState.
        """
        from ..agent.state import ThreadState as TS

        # Use thread_id as user_id (v1 simplification)
        user_id = state.thread_id or "default"
        project_slug = self.project_slug

        # Load combined memory context
        memory_context = self.memory_store.load(user_id, project_slug)

        # Store in state for builder to read
        if hasattr(state, "memory_context"):
            state.memory_context = memory_context  # type: ignore
        else:
            # Fallback: inject as a field (extend ThreadState if needed)
            state.memory_context = memory_context  # type: ignore

    async def after_agent_end(self, state: "ThreadState") -> None:
        """After agent ends - placeholder for v2 memory writing."""
        pass
