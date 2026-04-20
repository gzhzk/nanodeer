"""Memory storage: USER.md (user preferences) + MEMORY.md (long-term facts) + episodic (session logs)."""

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from .types import MemoryEntry

# Memory directory root (single-user, no user_id)
MEMORY_ROOT = Path.home() / ".nanodeer" / "memory"

EPISODIC_DIR = "episodic"
USER_FILE = "USER.md"
MEMORY_FILE = "MEMORY.md"


class MemoryStore:
    """USER.md + MEMORY.md + episodic storage."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or MEMORY_ROOT
        self._ensure_root()

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / EPISODIC_DIR).mkdir(exist_ok=True)

    # -------------------------------------------------------------------------
    # USER memory
    # -------------------------------------------------------------------------

    def load_user_memory(self) -> str:
        """Load USER.md - user preferences and context."""
        user_file = self.root / USER_FILE
        if not user_file.exists():
            return ""
        try:
            raw = user_file.read_text(encoding="utf-8").strip()
            if raw.startswith("---"):
                entry = MemoryEntry.from_frontmatter(raw)
                return entry.content
            return raw
        except Exception:
            return ""

    def save_user_memory(self, content: str) -> None:
        """Save USER.md - user preferences and context."""
        entry = MemoryEntry(
            name="user-memory",
            description="User preferences and context",
            memory_type="user",
            content=content,
        )
        user_file = self.root / USER_FILE
        user_file.write_text(entry.to_frontmatter(), encoding="utf-8")

    # -------------------------------------------------------------------------
    # General memory
    # -------------------------------------------------------------------------

    def load_memory(self) -> str:
        """Load MEMORY.md - long-term facts and knowledge."""
        memory_file = self.root / MEMORY_FILE
        if not memory_file.exists():
            return ""
        try:
            raw = memory_file.read_text(encoding="utf-8").strip()
            if raw.startswith("---"):
                entry = MemoryEntry.from_frontmatter(raw)
                return entry.content
            return raw
        except Exception:
            return ""

    def save_memory(self, content: str, mode: str = "append") -> None:
        """Save to MEMORY.md - LLM chooses append or replace.

        Args:
            content: The content to save.
            mode: "append" (default) adds to existing content.
                  "replace" overwrites entirely with new content.
        """
        if mode == "replace":
            merged = content.strip()
        else:
            existing = self.load_memory()
            merged = (existing + "\n\n" + content).strip()
        entry = MemoryEntry(
            name="long-term-memory",
            description="Long-term facts and knowledge",
            memory_type="user",
            content=merged,
        )
        memory_file = self.root / MEMORY_FILE
        memory_file.write_text(entry.to_frontmatter(), encoding="utf-8")

    # -------------------------------------------------------------------------
    # Episodic (session logs)
    # -------------------------------------------------------------------------

    def episodic_path(self, d: date) -> Path:
        """Path to episodic file for a given date."""
        return self.root / EPISODIC_DIR / f"{d.isoformat()}.md"

    def append_episodic(self, content: str, d: date | None = None) -> None:
        """Append raw content to episodic file for date.

        No extraction, no LLM call. Raw append only.
        """
        if not content:
            return
        path = self.episodic_path(d or date.today())
        existing = ""
        if path.exists():
            existing = path.read_text(encoding="utf-8").strip()
        sep = "\n\n---\n\n" if existing else ""
        path.write_text(existing + sep + content, encoding="utf-8")

    def load_episodic(self, d: date) -> str:
        """Load episodic file for a specific date."""
        path = self.episodic_path(d)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def load_recent_episodic(self) -> str:
        """Load today's and yesterday's episodic files combined."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        parts = []
        for d in [yesterday, today]:
            content = self.load_episodic(d)
            if content:
                parts.append(f"## {d.isoformat()}\n\n{content}")
        return "\n\n---\n\n".join(parts) if parts else ""

    def list_episodic(self) -> list[date]:
        """List all dates with episodic files."""
        episodic_dir = self.root / EPISODIC_DIR
        if not episodic_dir.exists():
            return []
        dates = []
        for f in episodic_dir.glob("*.md"):
            try:
                dates.append(date.fromisoformat(f.stem))
            except ValueError:
                continue
        return sorted(dates)

    # -------------------------------------------------------------------------
    # Prompt injection
    # -------------------------------------------------------------------------

    def load_for_prompt(self) -> str:
        """Load combined memories for prompt injection.

        Returns tagged content: USER + MEMORY + episodic.
        """
        parts = []
        user = self.load_user_memory()
        if user:
            parts.append(f"<user_memory>\n{user}\n</user_memory>")
        memory = self.load_memory()
        if memory:
            parts.append(f"<memory>\n{memory}\n</memory>")
        recent = self.load_recent_episodic()
        if recent:
            parts.append(f"<episodic>\n{recent}\n</episodic>")
        return "\n\n".join(parts)
