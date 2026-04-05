"""File-based memory storage for NanoDeer.

Storage structure:
~/.nanodeer/
└── memory/
    └── {user_id}/
        ├── MEMORY.md          # Index entry (max 200 lines)
        ├── user.md            # User preferences
        └── project/
            └── {slug}.md      # Project-specific memory
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .types import MemoryEntry, MEMORY_USER_TEMPLATE


# Memory directory root
MEMORY_ROOT = Path.home() / ".nanodeer" / "memory"

# Memory file names
USER_MEMORY_FILE = "user.md"
INDEX_FILE = "MEMORY.md"
PROJECT_DIR = "project"
MAX_INDEX_LINES = 200


class MemoryStore:
    """File-based memory storage.

    v1 focuses on read-only access. Writing will be added later.
    """

    def __init__(self, root: Optional[Path] = None):
        """Initialize memory store.

        Args:
            root: Custom root directory. Defaults to ~/.nanodeer/memory/
        """
        self.root = root or MEMORY_ROOT
        self._ensure_root()

    def _ensure_root(self) -> None:
        """Ensure memory root directory exists."""
        self.root.mkdir(parents=True, exist_ok=True)

    def _user_dir(self, user_id: str) -> Path:
        """Get memory directory for a user."""
        # Sanitize user_id to prevent path traversal
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", user_id)
        return self.root / safe_id

    def _project_dir(self, user_id: str) -> Path:
        """Get project memory directory for a user."""
        d = self._user_dir(user_id) / PROJECT_DIR
        d.mkdir(parents=True, exist_ok=True)
        return d

    # -------------------------------------------------------------------------
    # Read operations
    # -------------------------------------------------------------------------

    def load_user_memory(self, user_id: str) -> str:
        """Load user memory for a user.

        Args:
            user_id: User identifier.

        Returns:
            Memory content as string (without frontmatter), empty string if not found.
        """
        user_dir = self._user_dir(user_id)
        user_file = user_dir / USER_MEMORY_FILE

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

    def load_project_memory(self, user_id: str, project_slug: str) -> str:
        """Load project-specific memory.

        Args:
            user_id: User identifier.
            project_slug: Project identifier (slug format).

        Returns:
            Memory content as string (without frontmatter), empty string if not found.
        """
        # Sanitize slug
        safe_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", project_slug)
        project_file = self._project_dir(user_id) / f"{safe_slug}.md"

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

    def load(self, user_id: str, project_slug: str = "default") -> str:
        """Load combined memory context for injection into system prompt.

        Reads both user and project memory, combines them into a single
        context string suitable for injection.

        Args:
            user_id: User identifier.
            project_slug: Project identifier. Defaults to "default".

        Returns:
            Combined memory context string, empty if no memory exists.
        """
        parts = []

        user_memory = self.load_user_memory(user_id)
        if user_memory:
            parts.append(f"<user_memory>\n{user_memory}\n</user_memory>")

        project_memory = self.load_project_memory(user_id, project_slug)
        if project_memory:
            parts.append(f"<project_memory>\n{project_memory}\n</project_memory>")

        if not parts:
            return ""

        return "\n\n".join(parts)

    # -------------------------------------------------------------------------
    # Write operations (v2 - stub for now)
    # -------------------------------------------------------------------------

    def save_user_memory(
        self,
        user_id: str,
        content: str,
        name: str = "user",
        description: str = "User preferences and identity",
    ) -> None:
        """Save user memory (v2 feature).

        Args:
            user_id: User identifier.
            content: Memory content.
            name: Memory entry name.
            description: One-line description.
        """
        user_dir = self._user_dir(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        user_file = user_dir / USER_MEMORY_FILE

        entry = MemoryEntry(
            name=name,
            description=description,
            memory_type="user",
            content=content,
            updated_at=datetime.now().isoformat(),
        )
        user_file.write_text(entry.to_frontmatter(), encoding="utf-8")

    def save_project_memory(
        self,
        user_id: str,
        project_slug: str,
        content: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        """Save project memory (v2 feature).

        Args:
            user_id: User identifier.
            project_slug: Project identifier.
            content: Memory content.
            name: Memory entry name.
            description: One-line description.
        """
        safe_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", project_slug)
        project_file = self._project_dir(user_id) / f"{safe_slug}.md"

        entry = MemoryEntry(
            name=name or project_slug,
            description=description or f"Project: {project_slug}",
            memory_type="project",
            content=content,
            updated_at=datetime.now().isoformat(),
        )
        project_file.write_text(entry.to_frontmatter(), encoding="utf-8")

    def update_index(self, user_id: str) -> None:
        """Update MEMORY.md index for a user (v2 feature)."""
        user_dir = self._user_dir(user_id)
        index_file = user_dir / INDEX_FILE

        file_list = []
        user_file = user_dir / USER_MEMORY_FILE
        if user_file.exists():
            file_list.append(f"- user.md (user preferences)")

        project_dir = user_dir / PROJECT_DIR
        if project_dir.exists():
            for pf in project_dir.glob("*.md"):
                file_list.append(f"- project/{pf.name}")

        content = f"""# Memory Index

This directory contains NanoDeer memory files.

## Files

{chr(10).join(file_list) if file_list else "(empty)"}

---
_last_updated: {datetime.now().isoformat()}
"""
        # Limit to MAX_INDEX_LINES
        lines = content.splitlines()
        if len(lines) > MAX_INDEX_LINES:
            lines = lines[:MAX_INDEX_LINES]
        index_file.write_text("\n".join(lines), encoding="utf-8")

    # -------------------------------------------------------------------------
    # Utility
    # -------------------------------------------------------------------------

    def exists(self, user_id: str, project_slug: str = "default") -> bool:
        """Check if any memory exists for user/project."""
        user_dir = self._user_dir(user_id)
        user_file = user_dir / USER_MEMORY_FILE
        project_file = self._project_dir(user_id) / f"{project_slug}.md"
        return user_file.exists() or project_file.exists()