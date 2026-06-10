"""Memory storage: USER.md + MEMORY.md flat files.

Core memory module — no wiki, no episodic, no layers.
Those live in extension modules (wiki.py, layers.py) and are loaded separately.
"""

import os
from pathlib import Path
from typing import Optional


def _default_memory_root() -> Path:
    override = os.getenv("NANODEER_MEMORY_ROOT")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".nanodeer" / "memory"


MEMORY_ROOT = _default_memory_root()
USER_FILE = "USER.md"
MEMORY_FILE = "MEMORY.md"


class MemoryStore:
    """Flat-file memory: USER.md (preferences) + MEMORY.md (facts).

    No wiki, episodic, or layer logic — those are extension modules
    (memory/wiki.py, memory/layers.py) loaded separately.
    """

    def __init__(self, root: Optional[Path] = None):
        self.root = root or _default_memory_root()
        self.root.mkdir(parents=True, exist_ok=True)

    # -- USER.md ---------------------------------------------------------------

    def load_user_memory(self) -> str:
        """Load USER.md — user preferences and context."""
        user_file = self.root / USER_FILE
        if not user_file.exists():
            return ""
        try:
            return user_file.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def save_user_memory(self, content: str) -> None:
        """Write USER.md."""
        user_file = self.root / USER_FILE
        user_file.write_text(content.strip(), encoding="utf-8")

    # -- MEMORY.md -------------------------------------------------------------

    def load_memory(self) -> str:
        """Load MEMORY.md — long-term facts and knowledge."""
        memory_file = self.root / MEMORY_FILE
        if not memory_file.exists():
            return ""
        try:
            return memory_file.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def save_memory(self, content: str, mode: str = "append") -> None:
        """Write to MEMORY.md.

        Args:
            content: Text to save.
            mode: "append" (default) adds to existing. "replace" overwrites.
        """
        if mode == "replace":
            merged = content.strip()
        else:
            existing = self.load_memory()
            merged = (existing + "\n\n" + content).strip()
        memory_file = self.root / MEMORY_FILE
        memory_file.write_text(merged, encoding="utf-8")

    # -- Prompt injection ------------------------------------------------------

    def load_for_prompt(self, context_hint: Optional[str] = None) -> str:
        """USER.md + MEMORY.md formatted for prompt injection.

        Args:
            context_hint: Ignored in core (used by wiki extension).

        Returns:
            Tagged memory content string, or empty string if no memory.
        """
        parts = []
        user = self.load_user_memory()
        if user:
            parts.append(f"<user_memory>\n{user}\n</user_memory>")
        memory = self.load_memory()
        if memory:
            parts.append(f"<memory>\n{memory}\n</memory>")
        return "\n\n".join(parts)
