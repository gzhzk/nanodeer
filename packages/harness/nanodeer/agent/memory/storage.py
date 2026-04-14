"""File-based memory storage for NanoDeer.

L1: ThreadState.messages (native, no storage needed)
L2: Episodic — raw append-only daily logs (episodic/YYYY-MM-DD.md)
L3: Long-term — MEMORY.md (manually maintained or external cron job)

Storage structure:
~/.nanodeer/memory/
├── episodic/
│   └── YYYY-MM-DD.md   # Raw daily session log, append-only
└── MEMORY.md            # L3: long-term memory, external job updates
"""

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from .types import MemoryEntry

# Memory directory root (single-user, no user_id)
MEMORY_ROOT = Path.home() / ".nanodeer" / "memory"

EPISODIC_DIR = "episodic"
MEMORY_FILE = "MEMORY.md"


class MemoryStore:
    """File-based L2/L3 memory. L2 is append-only raw logs. L3 is external."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or MEMORY_ROOT
        self._ensure_root()

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / EPISODIC_DIR).mkdir(exist_ok=True)

    # -------------------------------------------------------------------------
    # L2: Episodic (raw append-only daily session logs)
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
    # L3: Long-term memory (MEMORY.md)
    # -------------------------------------------------------------------------

    def load_memory(self) -> str:
        """Load L3 long-term memory. Returns raw content, no tags."""
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

    def save_memory(
        self,
        content: str,
        name: str = "long-term-memory",
        description: str = "精选长期记忆",
    ) -> None:
        """Save L3 long-term memory (called by save_memory tool)."""
        entry = MemoryEntry(
            name=name,
            description=description,
            memory_type="user",
            content=content,
        )
        memory_file = self.root / MEMORY_FILE
        memory_file.write_text(entry.to_frontmatter(), encoding="utf-8")

    # -------------------------------------------------------------------------
    # Combined L2 + L3 load (for builder prompt injection)
    # Returns tagged content for consistent prompt formatting.
    # -------------------------------------------------------------------------

    def load(self) -> str:
        """Load combined L3 + recent episodic for prompt injection.

        Returns tagged content: <memory> for L3, <episodic> for recent logs.
        """
        parts = []
        l3 = self.load_memory()
        if l3:
            parts.append(f"<memory>\n{l3}\n</memory>")
        recent = self.load_recent_episodic()
        if recent:
            parts.append(f"<episodic>\n{recent}\n</episodic>")
        return "\n\n".join(parts)

    # -------------------------------------------------------------------------
    # Project memory
    # -------------------------------------------------------------------------

    def load_project_memory(self, project_slug: str) -> str:
        """Load project-specific memory."""
        safe_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", project_slug)
        project_file = self.root / "project" / f"{safe_slug}.md"
        if not project_file.exists():
            return ""
        try:
            raw = project_file.read_text(encoding="utf-8").strip()
            if raw.startswith("---"):
                entry = MemoryEntry.from_frontmatter(raw)
                return entry.content
            return raw
        except Exception:
            return ""

    def save_project_memory(
        self,
        project_slug: str,
        content: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        """Save project-specific memory."""
        safe_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", project_slug)
        project_dir = self.root / "project"
        project_dir.mkdir(exist_ok=True)
        project_file = project_dir / f"{safe_slug}.md"
        entry = MemoryEntry(
            name=name or project_slug,
            description=description or f"Project: {project_slug}",
            memory_type="project",
            content=content,
        )
        project_file.write_text(entry.to_frontmatter(), encoding="utf-8")

    # -------------------------------------------------------------------------
    # Todo operations (via plan loader)
    # -------------------------------------------------------------------------

    def load_todos(self, project_slug: str = "default") -> list[dict]:
        """Load todos for a project."""
        import json

        todos_file = self.root / "todos" / f"{project_slug}.json"
        if not todos_file.exists():
            return []
        try:
            data = json.loads(todos_file.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def save_todos(self, project_slug: str, todos: list[dict]) -> None:
        """Save todos for a project."""
        import json

        todos_dir = self.root / "todos"
        todos_dir.mkdir(exist_ok=True)
        todos_file = todos_dir / f"{project_slug}.json"
        todos_file.write_text(json.dumps(todos, indent=2, ensure_ascii=False))
