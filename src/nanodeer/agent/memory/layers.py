"""MemoryLayers — L1-L4 layered memory injection for prompt assembly.

Each layer has distinct access pattern, size characteristics, and pruning strategy:

  L4: Wiki entries       — structured key-value, searched by context_hint, top-k
  L2: USER.md            — user preferences, compact, full injection
  L3: MEMORY.md          — LLM-managed long-term facts, compact, full injection
  L1: Episodic (recent)  — auto-logged session history, unbounded, truncated

Rationale for ordering (wiki → user → memory → episodic):
  Most structured and valuable first; bulkiest and noisiest last.
  Prevents episodic log noise from crowding out wiki knowledge in the prompt window.
"""

import logging
from typing import TYPE_CHECKING

from .storage import MemoryStore

if TYPE_CHECKING:
    from ..state import ThreadState, TurnSignals

logger = logging.getLogger(__name__)

_EPISODIC_MAX_CHARS = 2000


class MemoryLayers:
    """L1-L4 layered memory injection.

    inject():  Assemble all layers into signals.memory_context (per-turn, read).
    absorb():  Auto-log current turn to episodic storage (post-turn, write).
    """

    def __init__(self, store: MemoryStore):
        self._store = store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def inject(
        self, signals: "TurnSignals", context_hint: str | None = None
    ) -> None:
        """Assemble L1-L4 memory into signals.memory_context.

        Order: L4 (wiki) → L2 (user) → L3 (memory) → L1 (episodic, truncated).
        """
        parts: list[str] = []

        # L4: Wiki — structured, searched by context
        wiki_entries = self._store.search_wiki(
            query=context_hint or "", max_entries=5
        )
        if wiki_entries:
            wiki_parts: list[str] = []
            for entry in wiki_entries:
                wiki_parts.append(
                    f'<wiki_entry path="{entry.path}" title="{entry.title}">\n'
                    f"{entry.content}\n</wiki_entry>"
                )
            parts.append(
                "<wiki_entries>\n" + "\n\n".join(wiki_parts) + "\n</wiki_entries>"
            )

        # L2: USER.md — compact, always
        user = self._store.load_user_memory()
        if user:
            parts.append(f"<user_memory>\n{user}\n</user_memory>")

        # L3: MEMORY.md — compact, always
        memory = self._store.load_memory()
        if memory:
            parts.append(f"<memory>\n{memory}\n</memory>")

        # L1: Episodic — recent only, truncated
        recent = self._store.load_recent_episodic()
        if recent:
            if len(recent) > _EPISODIC_MAX_CHARS:
                recent = "...[truncated]\n" + recent[-_EPISODIC_MAX_CHARS:]
            parts.append(f"<episodic>\n{recent}\n</episodic>")

        if parts:
            signals.memory_context = "\n\n".join(parts)

    def absorb(self, state: "ThreadState") -> None:
        """Auto-log the last turn to episodic storage.

        Captures the last user→AI exchange as raw text.
        No extraction or summarisation — that is the LLM's job via save_memory.
        Idempotent: no-op if there is no new user message.
        """
        if not state.messages:
            return

        # Walk backwards from the end to find the last user message,
        # collecting AI responses along the way.
        lines: list[str] = []
        for msg in reversed(state.messages):
            from ..messages import AIMessage, HumanMessage

            if isinstance(msg, HumanMessage):
                lines.append(f"user: {msg.content}")
                break
            if isinstance(msg, AIMessage) and msg.content:
                lines.append(f"ai: {msg.content[:500]}")

        if not lines:
            return

        # Reverse back to chronological order
        content = "\n".join(reversed(lines))
        self._store.append_episodic(content)
