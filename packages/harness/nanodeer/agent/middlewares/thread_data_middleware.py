"""ThreadDataMiddleware — initializes per-thread directory structure.

before_llm: creates workspace/uploads/outputs directories.
Does NOT participate in prompt logic — only physical directory initialization.
"""

from pathlib import Path
from typing import Optional

from nanodeer.agent.state import ThreadState

from .base import Middleware


class ThreadDataState:
    """Per-thread directory structure with physical path management."""

    def __init__(
        self,
        thread_id: str,
        base_path: Path,
        virtual_base: str = "/mnt/user-data",
    ):
        self.thread_id = thread_id
        self.base_path = base_path
        self.virtual_base = virtual_base
        self.workspace_path: Optional[str] = None
        self.uploads_path: Optional[str] = None
        self.outputs_path: Optional[str] = None

    def ensure_dirs(self) -> None:
        """Create all required directories."""
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.workspace_path = f"{self.virtual_base}/workspace"
        self.uploads_path = f"{self.virtual_base}/uploads"
        self.outputs_path = f"{self.virtual_base}/outputs"


class ThreadDataMiddleware(Middleware):
    """Initializes ThreadData and creates thread directory structure.

    Runs first in before_llm to ensure directories exist
    before any tool or middleware needs them.
    """

    def __init__(
        self,
        base_path: str | Path = "/tmp/nanodeer/threads",
        virtual_base: str = "/mnt/user-data",
    ):
        self.base_path = Path(base_path)
        self.virtual_base = virtual_base

    async def before_llm(self, state: ThreadState) -> None:
        """Create ThreadData and ensure directories exist."""
        if state.thread_data is not None:
            return

        if not state.sandbox or not state.sandbox.thread_id:
            return

        thread_data = ThreadDataState(
            thread_id=state.sandbox.thread_id,
            base_path=self.base_path / state.sandbox.thread_id,
            virtual_base=self.virtual_base,
        )
        thread_data.ensure_dirs()

        state.thread_data = thread_data