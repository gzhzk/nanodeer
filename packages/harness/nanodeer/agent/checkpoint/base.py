"""Checkpointer ABC — persist and resume ThreadState across process restarts."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nanodeer.agent.state import ThreadState


class Checkpointer(ABC):
    """Abstract checkpoint interface.

    save():  Called after each turn ends (after after_tools_all).
            State is complete and consistent at this point.

    load():  Called at run() start when thread_id is known but messages are empty.
            Returns restored ThreadState or None if no checkpoint exists.
    """

    @abstractmethod
    async def save(self, thread_id: str, state: "ThreadState") -> None:
        """Persist ThreadState for a thread."""
        ...

    @abstractmethod
    async def load(self, thread_id: str) -> "ThreadState | None":
        """Restore ThreadState for a thread. Returns None if no checkpoint found."""
        ...

    @abstractmethod
    async def list_threads(self) -> list[str]:
        """List all thread_ids that have a checkpoint."""
        ...
