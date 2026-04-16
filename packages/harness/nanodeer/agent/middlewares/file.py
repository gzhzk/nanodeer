"""FileMiddleware — writes user-uploaded files to host disk.

Writes to the host directory that is volume-mounted into the container,
so files are accessible at /mnt/user-data/uploads/ inside the sandbox.

before_llm: consumes state.metadata["uploaded_files"], writes to disk,
            writes virtual path list to state.metadata["_uploaded_paths"].
"""

import mimetypes
from pathlib import Path

from nanodeer.agent.state import ThreadState
from nanodeer.config import get_config

from .base import Middleware


class FileMiddleware(Middleware):
    """Writes uploaded files to host disk for container access."""

    def __init__(self, base_path: Path | None = None):
        cfg = get_config()
        self.base_path = base_path or cfg.thread.storage_path

    async def before_llm(self, state: ThreadState) -> None:
        if not state.thread_id:
            return

        uploaded_files = state.metadata.get("uploaded_files", [])
        if not uploaded_files:
            return

        virtual_uploads = "/mnt/user-data/uploads"
        root = self.base_path / state.thread_id / "user-data" / "uploads"
        root.mkdir(parents=True, exist_ok=True)

        paths = []
        for file_info in uploaded_files:
            if isinstance(file_info, dict):
                filename = file_info.get("name", "unknown")
                content = file_info.get("content", "")
            else:
                file_path = Path(file_info)
                filename = file_path.name
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    content = None

            dest = root / filename
            if content is not None:
                dest.write_text(content, encoding="utf-8")
            else:
                dest.touch()

            paths.append(f"{virtual_uploads}/{filename}")

        # Pass virtual paths to MemoryMiddleware and consume source
        state.metadata["_uploaded_paths"] = paths
        state.metadata["uploaded_files"] = []
