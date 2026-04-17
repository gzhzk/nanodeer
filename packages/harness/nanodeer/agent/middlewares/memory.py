"""MemoryMiddleware — loads memory context into signals.

before_llm:
  - Loads L3 + episodic + project memory from MemoryStore
  - Appends uploaded file summaries → signals.memory_context
"""

from nanodeer.agent.state import ThreadState, TurnSignals

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

    async def before_llm(self, state: ThreadState, signals: TurnSignals) -> None:
        if not self._memory_store:
            return

        project_slug = state.thread_id or "default"
        memory_context = self._memory_store.load_for_prompt(project_slug)

        # Append uploaded file summaries
        uploaded_files = getattr(signals, "_uploaded_files", None)
        if uploaded_files:
            lines = [f"- {f['name']}" for f in uploaded_files if isinstance(f, dict)]
            file_section = f"<uploaded_files>\n" + "\n".join(lines) + "\n</uploaded_files>"
            memory_context = (memory_context + "\n\n" + file_section).strip()

        if memory_context:
            signals.memory_context = memory_context
