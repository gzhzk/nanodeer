"""FileCheckpointer — persist ThreadState to disk as JSON."""

import json
from pathlib import Path
from typing import Any

from ..state import ThreadState
from .base import Checkpointer


class FileCheckpointer(Checkpointer):
    """Stores ThreadState as JSON under {storage_path}/{thread_id}/checkpoint.json.

    Storage layout:
        {storage_path}/{thread_id}/
            ├── user-data/         ← sandbox working dir
            ├── checkpoint.json   ← this module
            └── outputs/

    This checkpointer survives process restarts and enables session resume.
    """

    def __init__(self, storage_path: Path):
        self.storage_path = Path(storage_path).expanduser().resolve()

    def _checkpoint_path(self, thread_id: str) -> Path:
        return self.storage_path / thread_id / "checkpoint.json"

    async def save(self, thread_id: str, state: ThreadState) -> None:
        """Write ThreadState as JSON to checkpoint file."""
        cp_path = self._checkpoint_path(thread_id)
        cp_path.parent.mkdir(parents=True, exist_ok=True)
        cp_path.write_text(
            state.model_dump_json(indent=2),
            encoding="utf-8",
        )

    async def load(self, thread_id: str) -> ThreadState | None:
        """Load ThreadState from checkpoint file. Returns None if not found."""
        cp_path = self._checkpoint_path(thread_id)
        if not cp_path.exists():
            return None
        try:
            data = json.loads(cp_path.read_text(encoding="utf-8"))
            return ThreadState.model_validate(data)
        except (json.JSONDecodeError, Exception):
            return None

    async def list_threads(self) -> list[str]:
        """List all thread_ids that have a checkpoint file."""
        if not self.storage_path.exists():
            return []
        return [
            d.name
            for d in self.storage_path.iterdir()
            if d.is_dir() and (d / "checkpoint.json").exists()
        ]
