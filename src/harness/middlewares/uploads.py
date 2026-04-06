"""UploadsMiddleware - processes user-uploaded files and injects into context.

Stores files in uploads/ directory and makes their contents accessible
to the agent via memory_context or file system.
"""
import mimetypes
from pathlib import Path

from harness.agent.state import ThreadState
from harness.config import get_config

from .base import Middleware


class UploadsMiddleware(Middleware):
    """Processes uploaded files before agent starts.

    Handles:
    - Text files (txt, md, py, json, csv, etc.): read content directly
    - Binary files (pdf, docx, xlsx, images): note as uploaded, content via memory
    - Stores files in /mnt/user-data/uploads/{thread_id}/

    Files are described to the agent via memory_context.
    """

    def __init__(self, base_path: Path | None = None):
        self.config = get_config()
        self.base_path = base_path or self.config.thread.storage_path

    async def before_agent_start(self, state: ThreadState) -> None:
        """Process uploaded files and inject into context."""
        if not state.thread_id or not state.uploaded_files:
            return

        user_data = self.base_path / state.thread_id / "user-data"
        uploads_dir = user_data / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        uploaded_summaries = []

        for file_info in state.uploaded_files:
            # file_info can be a dict {name, content, mime_type} or just a path string
            if isinstance(file_info, dict):
                filename = file_info.get("name", "unknown")
                content = file_info.get("content", "")
                mime_type = file_info.get("mime_type", "")
            else:
                # Assume it's a file path - read from disk
                file_path = Path(file_info)
                filename = file_path.name
                mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    content = None

            # Write to uploads directory
            file_path = uploads_dir / filename
            if content is not None:
                file_path.write_text(content, encoding="utf-8")
            else:
                # Binary file - just note it exists
                file_path.touch()

            # Build summary for agent
            virtual_path = f"/mnt/user-data/uploads/{filename}"
            is_text = mime_type and mime_type.startswith("text/") or filename.endswith((".txt", ".md", ".py", ".json", ".csv", ".yml", ".yaml", ".xml", ".html", ".css", ".js", ".ts"))

            if content is not None and len(content) < 5000:
                # Small text file - include content
                summary = f"[Uploaded file: {filename}]\nPath: {virtual_path}\nContent:\n{content[:1000]}"
            elif content is not None:
                # Large text file - truncate
                summary = f"[Uploaded file: {filename}]\nPath: {virtual_path}\nContent (first 1000 chars):\n{content[:1000]}\n... (truncated, {len(content)} total chars)"
            else:
                # Binary file
                summary = f"[Uploaded file: {filename}]\nPath: {virtual_path}\nType: {mime_type}\n(Binary file - use appropriate tool to read)"

            uploaded_summaries.append(summary)

        # Inject into memory_context
        if uploaded_summaries:
            uploads_section = "\n\n".join(uploaded_summaries)
            existing = state.memory_context or ""
            state.memory_context = (
                f"{existing}\n\n<uploads>\n{uploads_section}\n</uploads>"
            ).strip()