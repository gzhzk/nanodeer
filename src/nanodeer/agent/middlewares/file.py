"""FileMiddleware — writes uploaded files to disk and injects file list into prompts.

before_llm_streaming: writes signals._uploaded_files to disk, then scans the
uploads/ directory to generate a formatted file list for the prompt's
<uploaded_files> section.
"""

import mimetypes
from pathlib import Path

from nanodeer.agent.state import ThreadState, TurnSignals
from nanodeer.config import get_config

from .base import Middleware


_TEXT_EXTENSIONS = frozenset({
    ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".conf", ".log", ".py", ".js", ".ts", ".jsx", ".tsx", ".html",
    ".htm", ".css", ".scss", ".sass", ".less", ".sh", ".bash", ".zsh",
    ".env", ".gitignore", ".dockerfile",
})

_TEXT_MIME_PREFIXES = ("text/", "application/json", "application/javascript",
                       "application/xml", "application/yaml", "application/toml")


class FileMiddleware(Middleware):
    """Writes uploaded files and scans uploads directory for prompt injection."""

    def __init__(self, base_path=None):
        cfg = get_config()
        self.base_path = base_path or cfg.thread.storage_path

    @staticmethod
    def _is_text_mime(mime_type: str, filename: str) -> bool:
        if not mime_type:
            ext = Path(filename).suffix.lower()
            return ext in _TEXT_EXTENSIONS
        return mime_type.startswith(_TEXT_MIME_PREFIXES)

    async def before_llm_streaming(self, state: ThreadState, signals: TurnSignals):
        if not state.thread_id:
            return
        yield

        upload_root = self.base_path / state.thread_id / "user-data" / "uploads"
        upload_root.mkdir(parents=True, exist_ok=True)

        # Write uploaded files to disk
        files_data = signals._uploaded_files
        if files_data:
            for f in files_data:
                name = f.get("name", "unnamed")
                content = f.get("content", b"")
                mime_type = f.get("mime_type", "")

                dest = upload_root / name
                is_text = self._is_text_mime(mime_type, name)
                if is_text:
                    try:
                        text = content.decode("utf-8") if isinstance(content, bytes) else content
                        dest.write_text(text, encoding="utf-8")
                    except (UnicodeDecodeError, UnicodeError):
                        dest.write_bytes(content if isinstance(content, bytes) else content.encode())
                else:
                    dest.write_bytes(content if isinstance(content, bytes) else content.encode())

        # Scan and report
        files = list(upload_root.iterdir())
        if not files:
            return

        lines = []
        for f in sorted(files):
            size = f.stat().st_size if f.is_file() else 0
            lines.append(f"- {f.name}" + (f" ({size} bytes)" if size else ""))

        signals.uploaded_files_list = "\n".join(lines)
