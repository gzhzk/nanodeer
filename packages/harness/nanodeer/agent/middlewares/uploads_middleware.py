"""UploadsMiddleware — processes user-uploaded files and injects into context.

Stores files in uploads/ directory and makes their contents accessible
to the agent via metadata["memory_context"].
"""

import mimetypes
from pathlib import Path

from nanodeer.agent.state import ThreadState
from nanodeer.config import get_config

from .base import Middleware


class UploadsMiddleware(Middleware):
    """Processes uploaded files before agent starts.

    Handles:
    - Text files (txt, md, py, json, csv, etc.): read content directly
    - Binary files (pdf, docx, xlsx, images): note as uploaded
    - Stores files in /mnt/user-data/uploads/{thread_id}/

    Files are described via metadata["memory_context"] for prompt rendering.
    """

    def __init__(self, base_path: Path | None = None):
        self.config = get_config()
        self.base_path = base_path or self.config.thread.storage_path

    async def before_llm(self, state: ThreadState) -> None:
        """Process uploaded files and inject into metadata."""
        if not state.sandbox or not state.sandbox.thread_id:
            return

        uploaded_files = state.metadata.get("uploaded_files", [])
        if not uploaded_files:
            return

        if state.thread_data:
            uploads_dir = Path(state.thread_data.uploads_path or "")
            if uploads_dir:
                uploads_dir.mkdir(parents=True, exist_ok=True)
        else:
            user_data = self.base_path / state.sandbox.thread_id / "user-data"
            uploads_dir = user_data / "uploads"
            uploads_dir.mkdir(parents=True, exist_ok=True)

        uploaded_summaries = []

        for file_info in uploaded_files:
            if isinstance(file_info, dict):
                filename = file_info.get("name", "unknown")
                content = file_info.get("content", "")
                mime_type = file_info.get("mime_type", "")
            else:
                file_path = Path(file_info)
                filename = file_path.name
                mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    content = None

            if state.thread_data:
                virtual_uploads = state.thread_data.uploads_path or "/mnt/user-data/uploads"
            else:
                virtual_uploads = "/mnt/user-data/uploads"

            file_path = uploads_dir / filename
            if content is not None:
                file_path.write_text(content, encoding="utf-8")
            else:
                file_path.touch()

            virtual_path = f"{virtual_uploads}/{filename}"
            is_text = mime_type and mime_type.startswith("text/") or filename.endswith(
                (".txt", ".md", ".py", ".json", ".csv", ".yml", ".yaml", ".xml", ".html", ".css", ".js", ".ts")
            )

            if content is not None and len(content) < 5000:
                summary = f"[Uploaded file: {filename}]\nPath: {virtual_path}\nContent:\n{content[:1000]}"
            elif content is not None:
                summary = f"[Uploaded file: {filename}]\nPath: {virtual_path}\nContent (first 1000 chars):\n{content[:1000]}\n... (truncated, {len(content)} total chars)"
            else:
                summary = f"[Uploaded file: {filename}]\nPath: {virtual_path}\nType: {mime_type}\n(Binary file - use appropriate tool to read)"

            uploaded_summaries.append(summary)

        if uploaded_summaries:
            uploads_section = "\n\n".join(uploaded_summaries)
            existing = state.metadata.get("memory_context") or ""
            state.metadata["memory_context"] = (
                f"{existing}\n\n<uploads>\n{uploads_section}\n</uploads>"
            ).strip()