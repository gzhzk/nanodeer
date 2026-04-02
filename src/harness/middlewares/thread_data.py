"""ThreadDataMiddleware - creates per-thread directory structure.

Each thread gets its own isolated workspace:
/workspace/{thread_id}/user-data/{workspace,uploads,outputs}

These directories are bind-mounted into the Docker sandbox container.
"""
import os
from pathlib import Path

from harness.agent.state import ThreadState
from harness.config import get_config

from .base import Middleware


class ThreadDataMiddleware(Middleware):
    """Creates and manages per-thread directory structures.

    Directory layout:
        {storage_path}/threads/{thread_id}/
            user-data/
                workspace/   # Agent's writable workspace
                uploads/     # User uploaded files
                outputs/     # Agent output files
    """

    def __init__(self, base_path: Path | None = None):
        """Initialize middleware.

        Args:
            base_path: Override base path for thread storage.
        """
        self.config = get_config()
        self.base_path = base_path or self.config.thread.storage_path

    async def before_agent_start(self, state: ThreadState) -> None:
        """Create thread directory structure before agent starts.

        Args:
            state: ThreadState (must have thread_id set).
        """
        if not state.thread_id:
            return

        thread_root = self.base_path / state.thread_id
        user_data = thread_root / "user-data"

        # Create directory structure
        dirs = [
            user_data / "workspace",
            user_data / "uploads",
            user_data / "outputs",
        ]

        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

        # Update sandbox working_dir
        if state.sandbox:
            state.sandbox.working_dir = str(user_data / "workspace")

    def get_thread_path(self, thread_id: str, *parts: str) -> Path:
        """Get path within thread's user-data directory.

        Args:
            thread_id: Thread identifier.
            parts: Path components relative to user-data/.

        Returns:
            Absolute path within thread's workspace.
        """
        return self.base_path / thread_id / "user-data" / "/".join(parts)