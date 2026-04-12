"""File-based memory storage for NanoDeer.

OpenClaw-inspired tiered memory:
- L1: Working memory (LLM context window, implicit)
- L2: Episodic memory — daily session logs (episodic/YYYY-MM-DD.md)
- L3: Long-term memory — distilled (MEMORY.md)

Storage structure:
~/.nanodeer/memory/
├── episodic/
│   ├── 2026-04-10.md   # Daily session log
│   └── 2026-04-09.md   # Yesterday's session
├── MEMORY.md           # L3: distilled long-term memory
└── project/
    └── {slug}.md       # Project-specific memory
"""

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from .types import MemoryEntry

# Memory directory root (single-user, no user_id)
MEMORY_ROOT = Path.home() / ".nanodeer" / "memory"

EPISODIC_DIR = "episodic"
PROJECT_DIR = "project"
TODOS_DIR = "todos"
MEMORY_FILE = "MEMORY.md"
TODOS_SUBDIR = "todos"

# Distillation triggers
DISTILL_FILE_COUNT = 30      # Trigger when episodic files > N
DISTILL_SIZE_KB = 100        # Trigger when total episodic > N KB


class MemoryStore:
    """File-based memory storage with L2/L3 tiered design."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or MEMORY_ROOT
        self._ensure_root()

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / EPISODIC_DIR).mkdir(exist_ok=True)
        (self.root / PROJECT_DIR).mkdir(exist_ok=True)

    # -------------------------------------------------------------------------
    # L2: Episodic (daily session logs)
    # -------------------------------------------------------------------------

    def episodic_path(self, d: date) -> Path:
        """Path to episodic file for a given date."""
        return self.root / EPISODIC_DIR / f"{d.isoformat()}.md"

    def save_episodic(self, content: str, d: date | None = None) -> None:
        """Append content to episodic file for date (creates if not exists).

        Args:
            content: Session log content to append.
            d: Date for the episodic file. Defaults to today.
        """
        path = self.episodic_path(d or date.today())
        existing = ""
        if path.exists():
            existing = path.read_text(encoding="utf-8").strip()
        sep = "\n\n---\n\n" if existing else ""
        path.write_text(existing + sep + content, encoding="utf-8")

    def load_episodic(self, d: date) -> str:
        """Load episodic file for a specific date.

        Args:
            d: Date to load.

        Returns:
            Content of the episodic file, or empty string if not found.
        """
        path = self.episodic_path(d)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def load_recent_episodic(self) -> str:
        """Load today's and yesterday's episodic files.

        Returns:
            Combined content of recent episodic files.
        """
        today = date.today()
        yesterday = today - timedelta(days=1)

        parts = []
        for d in [yesterday, today]:
            content = self.load_episodic(d)
            if content:
                parts.append(f"## {d.isoformat()}\n\n{content}")

        if not parts:
            return ""
        return "\n\n---\n\n".join(parts)

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
        """Load L3 long-term memory (MEMORY.md).

        Returns:
            Memory content without frontmatter, empty string if not found.
        """
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
        """Save L3 long-term memory.

        Args:
            content: Memory content.
            name: Memory entry name.
            description: One-line description.
        """
        entry = MemoryEntry(
            name=name,
            description=description,
            memory_type="user",
            content=content,
        )
        memory_file = self.root / MEMORY_FILE
        memory_file.write_text(entry.to_frontmatter(), encoding="utf-8")

    # -------------------------------------------------------------------------
    # Legacy compatibility (load/save as combined L3 + recent episodic)
    # -------------------------------------------------------------------------

    def load(self) -> str:
        """Load combined memory context for prompt injection.

        Combines L3 (MEMORY.md) + recent episodic (today + yesterday).

        Returns:
            Combined memory context string.
        """
        parts = []

        l3 = self.load_memory()
        if l3:
            parts.append(f"<memory>\n{l3}\n</memory>")

        recent = self.load_recent_episodic()
        if recent:
            parts.append(f"<recent_episodes>\n{recent}\n</recent_episodes>")

        if not parts:
            return ""
        return "\n\n".join(parts)

    # -------------------------------------------------------------------------
    # Full context (for builder)
    # -------------------------------------------------------------------------

    def load_full_context(self, project_slug: str = "default") -> str:
        """Load full memory context: L3 + episodic + project memory.

        Single method to call from builder — combines load() + project memory.
        """
        parts = []

        l3 = self.load_memory()
        if l3:
            parts.append(f"<memory>\n{l3}\n</memory>")

        recent = self.load_recent_episodic()
        if recent:
            parts.append(f"<recent_episodes>\n{recent}\n</recent_episodes>")

        project_mem = self.load_project_memory(project_slug)
        if project_mem:
            parts.append(f"<project_memory>\n{project_mem}\n</project_memory>")

        if not parts:
            return ""
        return "\n\n".join(parts)

    # -------------------------------------------------------------------------
    # Project memory
    # -------------------------------------------------------------------------

    def load_project_memory(self, project_slug: str) -> str:
        """Load project-specific memory.

        Args:
            project_slug: Project identifier.

        Returns:
            Memory content, empty string if not found.
        """
        safe_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", project_slug)
        project_file = self.root / PROJECT_DIR / f"{safe_slug}.md"

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
        """Save project-specific memory.

        Args:
            project_slug: Project identifier.
            content: Memory content.
            name: Memory entry name.
            description: One-line description.
        """
        safe_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", project_slug)
        project_dir = self.root / PROJECT_DIR
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
    # Distillation check
    # -------------------------------------------------------------------------

    def should_distill(self) -> bool:
        """Check if distillation should be triggered.

        Triggers when episodic files exceed threshold.
        """
        episodic_dir = self.root / EPISODIC_DIR
        if not episodic_dir.exists():
            return False

        files = list(episodic_dir.glob("*.md"))
        if len(files) > DISTILL_FILE_COUNT:
            return True

        total_size = sum(f.stat().st_size for f in files)
        if total_size > DISTILL_SIZE_KB * 1024:
            return True

        return False

    # -------------------------------------------------------------------------
    # Todo operations (unchanged)
    # -------------------------------------------------------------------------

    def _todos_dir(self) -> Path:
        d = self.root / TODOS_DIR
        d.mkdir(exist_ok=True)
        return d

    def load_todos(self, project_slug: str = "default") -> list[dict]:
        """Load todos for a project."""
        import json
        todos_file = self._todos_dir() / f"{project_slug}.json"
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
        todos_file = self._todos_dir() / f"{project_slug}.json"
        todos_file.write_text(json.dumps(todos, indent=2, ensure_ascii=False), encoding="utf-8")

    # -------------------------------------------------------------------------
    # Builder integration methods
    # -------------------------------------------------------------------------

    def extract_and_save(self, messages: list) -> None:
        """Extract key info from conversation and save as episodic.

        Saves the last exchange as episodic for later distillation.
        LLM-based extraction is async and done by external process.
        """
        if not messages:
            return

        # Save recent exchange as episodic
        recent = messages[-6:]  # last 6 messages
        formatted = []
        for msg in recent:
            role = type(msg).__name__
            content = msg.content if hasattr(msg, "content") else str(msg)
            formatted.append(f"[{role}]: {content[:500]}")

        episodic_content = "\n\n".join(formatted)
        if episodic_content:
            self.save_episodic(episodic_content)

    def handle_save_memory(self, tool_args: dict, original_result: str) -> str:
        """Intercept save_memory tool call and persist to storage.

        Args:
            tool_args: Tool arguments from save_memory call.
            original_result: Original tool result to pass through.

        Returns:
            Original result unchanged.
        """
        content = tool_args.get("content", "")
        if not content:
            return original_result

        category = tool_args.get("category", "user")
        project = tool_args.get("project", None)

        if project:
            self.save_project_memory(project, content)
        else:
            self.save_memory(content)

        return original_result

    # -------------------------------------------------------------------------
    # Legacy user memory (redirect to MEMORY.md)
    # -------------------------------------------------------------------------

    def load_user_memory(self) -> str:
        """Legacy: redirect to load_memory()."""
        return self.load_memory()

    def save_user_memory(
        self,
        content: str,
        name: str = "user-memory",
        description: str = "用户记忆",
    ) -> None:
        """Legacy: redirect to save_memory()."""
        self.save_memory(content, name, description)
