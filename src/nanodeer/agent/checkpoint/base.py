"""Checkpointer ABC — persist and resume AgentState across process restarts."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nanodeer.agent.state import AgentState


class Checkpointer(ABC):
    """Abstract checkpoint interface.

    save():  Called after each turn ends (after after_tools_all).
            State is complete and consistent at this point.

    load():  Called at run() start when thread_id is known but messages are empty.
            Returns restored AgentState or None if no checkpoint exists.
    """

    @abstractmethod
    async def save(self, thread_id: str, state: "AgentState") -> None:
        """Persist AgentState for a thread."""

    @abstractmethod
    async def delete(self, thread_id: str) -> bool:
        """Delete checkpoint for a thread. Returns True if deleted, False if not found."""
        ...

    @abstractmethod
    async def load(self, thread_id: str) -> "AgentState | None":
        """Restore AgentState for a thread. Returns None if no checkpoint found."""
        ...

    @abstractmethod
    async def list_threads(self) -> list[str]:
        """List all thread_ids that have a checkpoint."""
        ...
