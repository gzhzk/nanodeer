"""ThreadDataMiddleware — initializes thread context and metadata.

before_llm: ensures metadata dict exists, sets default paths.
"""

from nanodeer.agent.state import ThreadState

from .base import Middleware


class ThreadDataMiddleware(Middleware):
    """Initializes thread context before agent starts.

    Ensures metadata dict exists and sets default virtual paths.
    """

    async def before_llm(self, state: ThreadState) -> None:
        """Initialize metadata if not present."""
        if state.metadata is None:
            state.metadata = {}

        # Ensure default virtual paths are set
        if "uploads_path" not in state.metadata:
            state.metadata["uploads_path"] = "/mnt/user-data/uploads"
        if "workspace_path" not in state.metadata:
            state.metadata["workspace_path"] = "/mnt/user-data/workspace"
        if "outputs_path" not in state.metadata:
            state.metadata["outputs_path"] = "/mnt/user-data/outputs"