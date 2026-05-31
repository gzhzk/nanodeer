"""WikiStore — structured wiki knowledge curated by the LLM.

The LLM decides what to remember and how to organize it via save_memory.
WikiStore automatically maintains the index — the LLM never
touches index.json directly.

Design principle: Agent controls content, WikiStore controls index.
"""

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from .types import WikiEntry, WikiIndex

MEMORY_ROOT = Path.home() / ".nanodeer" / "memory"

WIKI_DIR = Path("wiki")
WIKI_ENTRIES_DIR = WIKI_DIR / "entries"
WIKI_INDEX_FILE = WIKI_DIR / "index.json"

# Characters NOT allowed in wiki entry paths (prevents traversal and special chars)
_INVALID_PATH_CHARS = re.compile(r"[^a-zA-Z0-9_\-/]")
_TRAVERSAL = re.compile(r"(?:^|/)\.\.(?:/|$)")


class WikiStore:
    """Structured wiki knowledge — CRUD, index management, tag-based retrieval.

    Thread-safe within a single process (not multi-process).
    """

    def __init__(self, root: Optional[Path] = None):
        self.root = root or MEMORY_ROOT
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Ensure wiki directory structure exists."""
        (self.root / WIKI_ENTRIES_DIR).mkdir(parents=True, exist_ok=True)
        # touch index.json if not exists
        index_path = self.root / WIKI_INDEX_FILE
        if not index_path.exists():
            self._write_index(WikiIndex())

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_path(path: str) -> str:
        """Validate and sanitize a wiki entry path.

        Rules:
          - No empty segments
          - No .. traversal
          - Only alphanumeric, _, -, /
          - No leading/trailing slashes
          - Max 200 chars

        Returns sanitized path or raises ValueError.
        """
        if not path or not path.strip():
            raise ValueError("Wiki path must not be empty")
        stripped = path.strip().strip("/")
        if _TRAVERSAL.search(stripped):
            raise ValueError(f"Path traversal blocked: {path!r}")
        sanitized = _INVALID_PATH_CHARS.sub("_", stripped)
        # Collapse multiple slashes
        sanitized = re.sub(r"/+", "/", sanitized)
        if len(sanitized) > 200:
            raise ValueError(f"Wiki path too long ({len(sanitized)} > 200): {path!r}")
        # Reject if entirely collapsed
        if not sanitized or sanitized == "_" * len(sanitized):
            raise ValueError(f"Wiki path contains only invalid characters: {path!r}")
        return sanitized

    def _entry_path(self, path: str) -> Path:
        """Get filesystem path for a wiki entry."""
        sanitized = self._sanitize_path(path)
        return self.root / WIKI_ENTRIES_DIR / f"{sanitized}.json"

    @staticmethod
    def _ensure_entry_dir(filepath: Path) -> None:
        """Create parent directory for an entry file if needed."""
        filepath.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Index operations
    # ------------------------------------------------------------------

    def _read_index(self) -> WikiIndex:
        """Read index from disk."""
        index_path = self.root / WIKI_INDEX_FILE
        if not index_path.exists():
            return WikiIndex()
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            entries = data.get("entries", {})
            # Ensure all entries have required fields
            cleaned = {}
            for key, val in entries.items():
                if isinstance(val, dict):
                    cleaned[key] = {
                        "title": val.get("title", key),
                        "summary": val.get("summary", ""),
                        "tags": val.get("tags", []),
                        "updated_at": val.get("updated_at", ""),
                    }
            return WikiIndex(
                version=data.get("version", 1),
                updated_at=data.get("updated_at", ""),
                entries=cleaned,
            )
        except (json.JSONDecodeError, OSError):
            return WikiIndex()

    def _write_index(self, index: WikiIndex) -> None:
        """Atomically write index using temp file + rename."""
        index_path = self.root / WIKI_INDEX_FILE
        index.updated_at = datetime.now().isoformat()
        data = {
            "version": index.version,
            "updated_at": index.updated_at,
            "entries": index.entries,
        }
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(dir=str(self.root / "wiki"), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, str(index_path))
        finally:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)

    def update_wiki_index(self, path: str, entry_meta: dict) -> None:
        """Update index for a single entry and write atomically."""
        index = self._read_index()
        index.entries[path] = {
            "title": entry_meta.get("title", path),
            "summary": entry_meta.get("summary", ""),
            "tags": entry_meta.get("tags", []),
            "updated_at": entry_meta.get("updated_at", datetime.now().isoformat()),
        }
        self._write_index(index)

    def remove_from_index(self, path: str) -> None:
        """Remove an entry from the index."""
        index = self._read_index()
        index.entries.pop(path, None)
        self._write_index(index)

    # ------------------------------------------------------------------
    # Entry CRUD
    # ------------------------------------------------------------------

    def save_wiki_entry(
        self,
        path: str,
        content: str,
        tags: Optional[list[str]] = None,
    ) -> WikiEntry:
        """Save a wiki entry (create or overwrite).

        Args:
            path: Category path like "project/language".
            content: Markdown content.
            tags: Optional list of tags for retrieval.

        Returns:
            The saved WikiEntry.
        """
        sanitized = self._sanitize_path(path)
        filepath = self._entry_path(sanitized)

        # Derive title from path if not embedded in content
        title = self._infer_title(sanitized)
        summary = self._infer_summary(content)

        tags_list = sorted(set(tags or []))
        now = datetime.now().isoformat()

        entry = WikiEntry(
            path=sanitized,
            title=title,
            summary=summary,
            content=content,
            tags=tags_list,
            updated_at=now,
        )

        self._ensure_entry_dir(filepath)
        filepath.write_text(
            json.dumps({
                "path": entry.path,
                "title": entry.title,
                "summary": entry.summary,
                "content": entry.content,
                "tags": entry.tags,
                "updated_at": entry.updated_at,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Update index
        self.update_wiki_index(sanitized, {
            "title": title,
            "summary": summary,
            "tags": tags_list,
            "updated_at": now,
        })

        return entry

    def load_wiki_entry(self, path: str) -> Optional[WikiEntry]:
        """Load a wiki entry by path. Returns None if not found."""
        sanitized = self._sanitize_path(path)
        filepath = self._entry_path(sanitized)
        if not filepath.exists():
            return None
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            return WikiEntry(
                path=data.get("path", sanitized),
                title=data.get("title", sanitized),
                summary=data.get("summary", ""),
                content=data.get("content", ""),
                tags=data.get("tags", []),
                updated_at=data.get("updated_at", ""),
            )
        except (json.JSONDecodeError, OSError):
            return None

    def delete_wiki_entry(self, path: str) -> bool:
        """Delete a wiki entry. Returns True if deleted, False if not found."""
        sanitized = self._sanitize_path(path)
        filepath = self._entry_path(sanitized)
        if not filepath.exists():
            return False
        filepath.unlink()
        self.remove_from_index(sanitized)
        return True

    def list_wiki_entries(self, tag: Optional[str] = None) -> list[dict]:
        """List all wiki entries from index, optionally filtered by tag.

        Returns list of dicts: {path, title, summary, tags, updated_at}
        Sorted by updated_at descending (newest first).
        """
        index = self._read_index()
        results = []
        for entry_path, meta in index.entries.items():
            if tag and tag not in meta.get("tags", []):
                continue
            results.append({
                "path": entry_path,
                "title": meta.get("title", entry_path),
                "summary": meta.get("summary", ""),
                "tags": meta.get("tags", []),
                "updated_at": meta.get("updated_at", ""),
            })
        results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return results

    def list_wiki_categories(self) -> list[str]:
        """List all category directories under entries/."""
        entries_dir = self.root / WIKI_ENTRIES_DIR
        if not entries_dir.exists():
            return []
        categories = set()
        for p in entries_dir.rglob("*.json"):
            rel = p.relative_to(entries_dir)
            parts = rel.parts[:-1]  # exclude filename
            if parts:
                categories.add(str(Path(*parts)))
        return sorted(categories)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_wiki(
        self,
        tags: Optional[list[str]] = None,
        query: str = "",
        max_entries: int = 5,
    ) -> list[WikiEntry]:
        """Search wiki entries by tag matching and keyword.

        Strategy (Phase 1):
          1. Load index.
          2. Score entries by: tag matches (weight 3) + keyword hits in
             title/summary (weight 1).
          3. Sort by score desc, then updated_at desc.
          4. Return Top N full entries.

        Args:
            tags: Tags to match (from current conversation context).
            query: Raw text for keyword matching in title/summary.
            max_entries: Max entries to return (default 5).

        Returns:
            List of matching WikiEntry objects (full content).
        """
        index = self._read_index()
        if not index.entries:
            return []

        query_lower = query.lower()
        query_keywords = {
            w for w in re.split(r"[\s,;:.!?()\[\]{}]+", query_lower)
            if len(w) > 2
        } if query else set()

        # Score each entry
        scored: list[tuple[float, str]] = []
        for entry_path, meta in index.entries.items():
            score = 0.0
            entry_tags = [t.lower() for t in meta.get("tags", [])]

            # Tag matching
            if tags:
                tag_hits = sum(1 for t in tags if t.lower() in entry_tags)
                score += tag_hits * 3.0

            # Keyword matching in title/summary
            if query_keywords:
                text = (meta.get("title", "") + " " + meta.get("summary", "")).lower()
                kw_hits = sum(1 for kw in query_keywords if kw in text)
                score += kw_hits * 1.0

            scored.append((score, entry_path))

        # Sort: score desc, then updated_at desc as tiebreaker
        scored.sort(key=lambda x: (-x[0], index.entries[x[1]].get("updated_at", "")))

        # Take top N with score > 0, or top N most recent if no query
        if tags or query:
            top_paths = [p for s, p in scored if s > 0][:max_entries]
        else:
            top_paths = [p for _, p in scored][:max_entries]

        # Load full entries
        results = []
        for entry_path in top_paths:
            entry = self.load_wiki_entry(entry_path)
            if entry:
                results.append(entry)

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_title(path: str) -> str:
        """Derive a human-readable title from a wiki path."""
        # "project/language" → "Project Language"
        parts = path.replace("-", " ").replace("_", " ").split("/")
        return " / ".join(p.strip().title() for p in parts if p.strip())

    @staticmethod
    def _infer_summary(content: str) -> str:
        """Extract summary from content: first non-empty line, ≤200 chars."""
        for line in content.splitlines():
            line = line.strip().strip("#").strip()
            if line:
                return line[:200]
        return ""
