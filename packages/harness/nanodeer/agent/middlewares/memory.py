"""MemoryMiddleware — loads memory context and todos into state.

before_llm:
  - Loads L3 + episodic + project memory from MemoryStore
    and appends uploaded file summaries → state.metadata["memory_context"]
  - Loads todos from plan_loader (or MemoryStore) → state.todos
"""

from nanodeer.agent.state import ThreadState

from .base import Middleware


class MemoryMiddleware(Middleware):
    """Loads memory and todos into state before LLM call."""

    def __init__(
        self,
        memory_store=None,
        plan_loader=None,
    ):
        self._memory_store = memory_store
        self._plan_loader = plan_loader

    async def before_llm(self, state: ThreadState) -> None:
        if not self._memory_store:
            return

        memory_context = self._memory_store.load_for_prompt(project_slug)

        # Append uploaded file summaries
        uploaded_paths = state.metadata.get("_uploaded_paths", [])
        if uploaded_paths:
            lines = [f"- {p}" for p in uploaded_paths]
            file_section = f"<uploaded_files>\n" + "\n".join(lines) + "\n</uploaded_files>"
            memory_context = (memory_context + "\n\n" + file_section).strip()

        if memory_context:
            state.metadata["memory_context"] = memory_context
