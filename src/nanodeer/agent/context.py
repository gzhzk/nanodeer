"""ContextManager — loads memory context before each ReAct turn.

Single async load() call that:
  1. Loads memory (USER.md + MEMORY.md)
  2. Writes uploaded files to disk
  3. Scans uploads for prompt visibility

No plan, no memory layers, no subagent — those are extension modules.
"""

import asyncio
import logging
from pathlib import Path

from nanodeer.agent.memory.storage import MemoryStore
from nanodeer.agent.messages import HumanMessage
from nanodeer.agent.state import ThreadState, TurnSignals
from nanodeer.config import get_config

logger = logging.getLogger(__name__)

_TEXT_EXTENSIONS = frozenset({
    ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".conf", ".log", ".py", ".js", ".ts", ".jsx", ".tsx", ".html",
    ".htm", ".css", ".scss", ".sass", ".less", ".sh", ".bash", ".zsh",
    ".env", ".gitignore", ".dockerfile",
})

_TEXT_MIME_PREFIXES = ("text/", "application/json", "application/javascript",
                       "application/xml", "application/yaml", "application/toml")


class ContextManager:
    """Loads memory context and uploads before each turn."""

    def __init__(self, memory_store=None):
        self._memory_store = memory_store or MemoryStore()
        self._cfg = get_config()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def load(self, state: ThreadState, signals: TurnSignals) -> None:
        """Load memory + uploads in parallel, writing into signals."""
        if not state.thread_id:
            return

        memory_task = asyncio.create_task(self._load_memory(state, signals))

        if signals.uploaded_files:
            await self._process_uploads(state, signals)
        await self._scan_uploads(state, signals)

        await memory_task

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_last_user_message(self, state: ThreadState) -> str:
        for msg in reversed(state.messages):
            if isinstance(msg, HumanMessage):
                content = msg.content
                return content if isinstance(content, str) else str(content or "")
        return ""

    async def _load_memory(self, state: ThreadState, signals: TurnSignals) -> None:
        """Load USER.md + MEMORY.md into signals as tagged prompt context."""
        context_hint = self._get_last_user_message(state) or None
        signals.memory_context = self._memory_store.load_for_prompt(context_hint=context_hint)

    async def _process_uploads(self, state: ThreadState, signals: TurnSignals) -> None:
        """Write uploaded files to disk."""
        root = self._cfg.thread.storage_path / state.thread_id / "user-data" / "uploads"
        root.mkdir(parents=True, exist_ok=True)

        for f in (signals.uploaded_files or []):
            name = Path(str(f.get("name", "unnamed"))).name or "unnamed"
            content = f.get("content", b"")
            mime_type = f.get("mime_type", "")
            dest = root / name

            ext = Path(name).suffix.lower()
            is_text = mime_type.startswith(_TEXT_MIME_PREFIXES) or ext in _TEXT_EXTENSIONS
            if is_text:
                try:
                    text = content.decode("utf-8") if isinstance(content, bytes) else content
                    dest.write_text(text, encoding="utf-8")
                except (UnicodeDecodeError, UnicodeError):
                    dest.write_bytes(content if isinstance(content, bytes) else content.encode())
            else:
                dest.write_bytes(content if isinstance(content, bytes) else content.encode())

    async def _scan_uploads(self, state: ThreadState, signals: TurnSignals) -> None:
        """Scan uploads dir and inject file list into signals."""
        upload_root = self._cfg.thread.storage_path / state.thread_id / "user-data" / "uploads"
        if not upload_root.exists():
            return

        files = sorted(upload_root.iterdir())
        if not files:
            return

        lines = []
        for f in files:
            size = f.stat().st_size if f.is_file() else 0
            size_label = f" ({size} bytes)" if size else ""
            lines.append(f"- {f.name} -> {f.resolve()}{size_label}")

        signals.uploaded_files_list = "\n".join(lines)
