"""FileMiddleware — writes user-uploaded files to host disk.

Writes to the host directory that is volume-mounted into the container,
so files are accessible at /mnt/user-data/uploads/ inside the sandbox.

before_llm: reads signals._uploaded_files (injected by executor), writes to disk.
"""

import mimetypes
from pathlib import Path

from nanodeer.agent.state import ThreadState, TurnSignals
from nanodeer.config import get_config

from .base import Middleware

_TEXT_MIME_TYPES = frozenset({
    "text/plain", "text/html", "text/css", "text/csv", "text/markdown",
    "text/xml", "application/json", "application/javascript",
    "application/xml", "application/csv",
})


class FileMiddleware(Middleware):
    """Writes uploaded files to host disk for container access."""

    def __init__(self, base_path: Path | None = None):
        cfg = get_config()
        self.base_path = base_path or cfg.thread.storage_path

    async def before_llm(self, state: ThreadState, signals: TurnSignals) -> None:
        if not state.thread_id:
            return

        uploaded_files = getattr(signals, "_uploaded_files", None)
        if not uploaded_files:
            return

        virtual_uploads = "/mnt/user-data/uploads"
        root = self.base_path / state.thread_id / "user-data" / "uploads"
        root.mkdir(parents=True, exist_ok=True)

        for file_info in uploaded_files:
            if not isinstance(file_info, dict):
                continue
            filename = file_info.get("name", "unknown")
            content = file_info.get("content", b"") or b""

            dest = root / filename
            mime_type = file_info.get("mime_type", "")

            if self._is_text_mime(mime_type, filename):
                try:
                    text = content.decode("utf-8")
                    dest.write_text(text, encoding="utf-8")
                except UnicodeDecodeError:
                    dest.write_bytes(content)
            else:
                dest.write_bytes(content)

    def _is_text_mime(self, mime_type: str, filename: str) -> bool:
        if mime_type:
            return mime_type.startswith("text/") or mime_type in _TEXT_MIME_TYPES
        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            return guessed.startswith("text/") or guessed in _TEXT_MIME_TYPES
        return filename.endswith((".txt", ".md", ".csv", ".json", ".xml", ".html", ".css", ".js", ".ts"))
