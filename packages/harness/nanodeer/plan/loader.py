"""Plan module - task tracking and planning."""

import json
from pathlib import Path

from .types import TodoItem, TodoStatus, TODOS_SECTION_TEMPLATE

__all__ = [
    "TodoItem",
    "TodoStatus",
    "TODOS_SECTION_TEMPLATE",
    "TodoStore",
]


class TodoStore:
    """File-based todo storage, independent of MemoryStore."""

    def __init__(self, root: Path | None = None):
        from ..agent.memory.storage import MEMORY_ROOT
        self._root = root or (MEMORY_ROOT.parent / "todos")
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, project_slug: str) -> Path:
        safe_slug = project_slug.replace("/", "_").replace("\\", "_")
        return self._root / f"{safe_slug}.json"

    def load(self, project_slug: str = "default") -> list[dict]:
        """Load todos for a project. Returns list of dicts."""
        path = self._path(project_slug)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def save(self, project_slug: str, todos: list[dict]) -> None:
        """Save todos for a project."""
        path = self._path(project_slug)
        path.write_text(json.dumps(todos, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_for_prompt(self, project_slug: str = "default") -> str:
        """Load todos formatted for prompt injection."""
        todos = self.load(project_slug)
        if not todos:
            return ""
        lines = [TodoItem.from_dict(t).to_markdown() for t in todos]
        return TODOS_SECTION_TEMPLATE.format(todos="\n".join(lines))
