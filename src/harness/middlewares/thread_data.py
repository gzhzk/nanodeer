"""ThreadDataMiddleware - creates per-thread directory structure.

Creates: {storage_path}/threads/{thread_id}/user-data/{workspace,uploads,outputs}
"""
from pathlib import Path

from harness.agent.state import ThreadState
from harness.config import get_config

from .base import Middleware


class ThreadDataMiddleware(Middleware):
    """Creates and manages per-thread directory structures."""

    def __init__(self, base_path: Path | None = None):
        self.config = get_config()
        self.base_path = base_path or self.config.thread.storage_path

    async def before_agent_start(self, state: ThreadState) -> None:
        """Create thread directory structure."""
        if not state.thread_id:
            return

        user_data = self.base_path / state.thread_id / "user-data"

        for subdir in ["workspace", "uploads", "outputs"]:
            (user_data / subdir).mkdir(parents=True, exist_ok=True)

        # Bind sandbox working_dir to workspace
        if state.sandbox:
            state.sandbox.working_dir = str(user_data / "workspace")

    def get_thread_path(self, thread_id: str, *parts: str) -> Path:
        """Get path within thread's user-data directory."""
        return self.base_path / thread_id / "user-data" / "/".join(parts)