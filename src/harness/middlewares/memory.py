"""Memory middleware for loading memory context before agent starts.

v1: Read-only - loads user + project memory into state.memory_context.
v2: Auto-extract - after_agent_end triggers LLM extraction and saving.
"""

from typing import TYPE_CHECKING, Any, Optional

from .base import Middleware

if TYPE_CHECKING:
    from ..memory.storage import MemoryStore
    from ..memory.extractor import MemoryExtractor


class MemoryMiddleware(Middleware):
    """Loads memory context into ThreadState before agent starts.

    v1 focuses on read-only: loads user + project memory from file storage
    and injects it into state.memory_context. The builder reads this field
    when constructing the system prompt.

    v2 adds auto-extraction: after_agent_end extracts key information from
    the conversation and saves it to memory files.

    Storage: ~/.nanodeer/memory/{user_id}/
    """

    def __init__(
        self,
        memory_store: "MemoryStore",
        project_slug: str = "default",
        extractor: Optional["MemoryExtractor"] = None,
        auto_extract: bool = True,
    ):
        """Initialize MemoryMiddleware.

        Args:
            memory_store: MemoryStore instance for reading/writing memory files.
            project_slug: Project identifier for project-specific memory.
                         Defaults to "default".
            extractor: MemoryExtractor instance for auto-extraction. Required for v2.
            auto_extract: Whether to auto-extract memories after agent ends.
                        Defaults to True.
        """
        self.memory_store = memory_store
        self.project_slug = project_slug
        self.extractor = extractor
        self.auto_extract = auto_extract

    async def before_agent_start(self, state: Any) -> None:
        """Load memory context into state.

        Reads user and project memory from file storage and stores the
        combined context in state.memory_context for prompt injection.

        Args:
            state: Current ThreadState (or dict).
        """
        # Handle both ThreadState and dict
        if isinstance(state, dict):
            thread_id = state.get("thread_id") or "default"
        else:
            thread_id = getattr(state, "thread_id", None) or "default"

        # Load combined memory context
        memory_context = self.memory_store.load(thread_id, self.project_slug)

        # Store in state for builder to read
        if isinstance(state, dict):
            state["memory_context"] = memory_context
        else:
            state.memory_context = memory_context  # type: ignore

    async def after_agent_end(self, result: dict) -> None:
        """Extract and save memories after agent ends.

        Args:
            result: Final state dict from agent execution (contains 'messages').
        """
        if not self.auto_extract or self.extractor is None:
            return

        messages = result.get("messages", [])
        if not messages:
            return

        # Extract memories from conversation
        extracted = await self.extractor.extract(messages)

        # Save each extracted memory
        for mem in extracted:
            if mem.category == "user":
                self.memory_store.save_user_memory(
                    user_id="default",
                    content=mem.content,
                    name=mem.name,
                    description=mem.description,
                )
            else:
                self.memory_store.save_project_memory(
                    user_id="default",
                    project_slug=self.project_slug,
                    content=mem.content,
                    name=mem.name,
                    description=mem.description,
                )

    async def after_tool_call(
        self, state: Any, tool_name: str, tool_args: dict, result: str
    ) -> None:
        """Intercept SaveMemory tool calls to save memories.

        Args:
            state: Current ThreadState (or dict).
            tool_name: Name of the tool that was called.
            tool_args: Arguments passed to the tool.
            result: Tool execution result.
        """
        if tool_name != "SaveMemory":
            return

        # Extract memory content and category from tool call
        content = tool_args.get("content", "")
        category = tool_args.get("category", "general")

        if not content:
            return

        # Map category string to memory type
        if category in ("user", "feedback"):
            self.memory_store.save_user_memory(
                user_id="default",
                content=content,
                name=f"Manual save: {content[:30]}...",
                description=f"User saved: {category}",
            )
        else:
            # project, api, style, decision -> project memory
            self.memory_store.save_project_memory(
                user_id="default",
                project_slug=self.project_slug,
                content=content,
                name=f"Manual save: {content[:30]}...",
                description=f"User saved: {category}",
            )
