"""ThreadDataMiddleware — creates thread directory structure.

Creates on host (before Docker mounts):
  {base_path}/{thread_id}/user-data/
  ├── workspace/
  ├── uploads/
  └── outputs/

These are volume-mounted into the container at /mnt/user-data/.
"""

from nanodeer.agent.state import ThreadState, TurnSignals
from nanodeer.config import get_config

from .base import Middleware


class ThreadDataMiddleware(Middleware):
    """Ensures thread directories exist before agent execution."""

    async def before_llm_streaming(self, state: ThreadState, signals: TurnSignals):
        if not state.thread_id:
            return
        yield  # make it an async generator

        cfg = get_config()
        base = cfg.thread.storage_path
        root = base / state.thread_id / "user-data"

        # Create all three directories eagerly
        (root / "workspace").mkdir(parents=True, exist_ok=True)
        (root / "uploads").mkdir(parents=True, exist_ok=True)
        (root / "outputs").mkdir(parents=True, exist_ok=True)
