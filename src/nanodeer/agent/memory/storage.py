"""Memory storage: USER.md (user preferences) + MEMORY.md (long-term facts) + episodic (session logs) + wiki (structured knowledge)."""

import os
import json
import re
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from .types import MemoryEntry, WikiEntry
from .wiki import WikiStore

def _default_memory_root() -> Path:
    override = os.getenv("NANODEER_MEMORY_ROOT")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".nanodeer" / "memory"


# Memory directory root (single-user, no user_id)
MEMORY_ROOT = _default_memory_root()

EPISODIC_DIR = "episodic"
USER_FILE = "USER.md"
MEMORY_FILE = "MEMORY.md"
WIKI_DIR = Path("wiki")
WIKI_ENTRIES_DIR = WIKI_DIR / "entries"
WIKI_INDEX_FILE = WIKI_DIR / "index.json"


class MemoryStore:
    """USER.md + MEMORY.md + episodic + wiki storage."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or _default_memory_root()
        self._wiki = WikiStore(root=self.root)
        self._ensure_root()

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / EPISODIC_DIR).mkdir(exist_ok=True)
        # wiki dirs are created by WikiStore.__init__

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
    # Wiki operations (delegated to WikiStore)
    # -------------------------------------------------------------------------

    def save_wiki_entry(
        self, path: str, content: str, tags: Optional[list[str]] = None
    ) -> WikiEntry:
        """Save a wiki entry (create or overwrite)."""
        return self._wiki.save_wiki_entry(path, content, tags=tags)

    def load_wiki_entry(self, path: str) -> Optional[WikiEntry]:
        """Load a wiki entry by path."""
        return self._wiki.load_wiki_entry(path)

    def delete_wiki_entry(self, path: str) -> bool:
        """Delete a wiki entry."""
        return self._wiki.delete_wiki_entry(path)

    def search_wiki(
        self,
        tags: Optional[list[str]] = None,
        query: str = "",
        max_entries: int = 5,
    ) -> list[WikiEntry]:
        """Search wiki entries by tag and keyword matching."""
        return self._wiki.search_wiki(tags=tags, query=query, max_entries=max_entries)

    def list_wiki_entries(self, tag: Optional[str] = None) -> list[dict]:
        """List wiki entries from index, optionally filtered by tag."""
        return self._wiki.list_wiki_entries(tag=tag)

    def list_wiki_categories(self) -> list[str]:
        """List all wiki category directories."""
        return self._wiki.list_wiki_categories()

    # -------------------------------------------------------------------------
    # Prompt injection
    # -------------------------------------------------------------------------

    def load_for_prompt(self, context_hint: str | None = None) -> str:
        """Load combined memories for prompt injection.

        v2 注入顺序（含 Wiki）：
        1. USER.md（用户偏好，全量）
        2. Wiki 条目（按 context_hint 检索匹配的条目）
        3. MEMORY.md（长期记忆，全量）
        4. episodic/（仅今日+昨日摘要）

        Args:
            context_hint: Current user message for wiki retrieval context.
                          Pass None to skip wiki search (fallback to recent entries).

        Returns:
            Tagged memory content string.
        """
        parts = []

        # 1. USER.md always
        user = self.load_user_memory()
        if user:
            parts.append(f"<user_memory>\n{user}\n</user_memory>")

        # 2. Wiki entries — search by context or load recent
        wiki_entries = self.search_wiki(query=context_hint or "", max_entries=5)
        if wiki_entries:
            wiki_parts = []
            for entry in wiki_entries:
                wiki_parts.append(
                    f'<wiki_entry path="{entry.path}" title="{entry.title}">\n'
                    f"{entry.content}\n"
                    f"</wiki_entry>"
                )
            parts.append(f"<wiki_entries>\n" + "\n\n".join(wiki_parts) + "\n</wiki_entries>")

        # 3. MEMORY.md (legacy)
        memory = self.load_memory()
        if memory:
            parts.append(f"<memory>\n{memory}\n</memory>")

        # 4. Recent episodic
        recent = self.load_recent_episodic()
        if recent:
            parts.append(f"<episodic>\n{recent}\n</episodic>")

        return "\n\n".join(parts)
