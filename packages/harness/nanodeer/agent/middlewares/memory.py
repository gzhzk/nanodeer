"""MemoryMiddleware — loads memory context into signals.

before_llm:
  - Loads USER + MEMORY + episodic from MemoryStore
  - Appends uploaded file summaries → signals.memory_context
"""

from nanodeer.agent.state import ThreadState, TurnSignals

from .base import Middleware


class MemoryMiddleware(Middleware):
    """Loads memory into state before LLM call."""

    def __init__(self, memory_store=None):
        self._memory_store = memory_store

    async def before_llm(self, state: ThreadState, signals: TurnSignals) -> None:
        if not self._memory_store:
            return

        memory_context = self._memory_store.load_for_prompt()

        # Append uploaded file summaries
        uploaded_files = getattr(signals, "_uploaded_files", None)
        if uploaded_files:
            lines = [f"- {f['name']}" for f in uploaded_files if isinstance(f, dict)]
            file_section = f"<uploaded_files>\n" + "\n".join(lines) + "\n</uploaded_files>"
            memory_context = (memory_context + "\n\n" + file_section).strip()

        if memory_context:
            signals.memory_context = memory_context
