"""FileMiddleware — discovers uploaded files and injects list into signals.

App layer writes files to the host mount point ({thread_id}/user-data/uploads/).
This middleware scans that directory and generates a formatted file list
for the prompt's <uploaded_files> section.

before_llm_streaming: scans uploads/ directory, injects signals.uploaded_files_list.
"""

from nanodeer.agent.state import ThreadState, TurnSignals
from nanodeer.config import get_config

from .base import Middleware


class FileMiddleware(Middleware):
    """Scans uploads directory and generates file list for prompt injection."""

    def __init__(self, base_path=None):
        cfg = get_config()
        self.base_path = base_path or cfg.thread.storage_path

    async def before_llm_streaming(self, state: ThreadState, signals: TurnSignals):
        if not state.thread_id:
            return
        yield  # make it an async generator

        root = self.base_path / state.thread_id / "user-data" / "uploads"
        if not root.exists():
            return

        files = list(root.iterdir())
        if not files:
            return

        lines = []
        for f in files:
            size = f.stat().st_size if f.is_file() else 0
            lines.append(f"- {f.name}" + (f" ({size} bytes)" if size else ""))

        signals.uploaded_files_list = "\n".join(lines)
