"""Memory module for NanoDeer — file-based L2/L3 storage.

L1: ThreadState.messages (ReAct loop, native)
L2: Episodic — raw append-only daily logs, agent reads via load_memory tool
L3: MEMORY.md — manually maintained or external cron job updates
"""

from .storage import MemoryStore
from .types import MemoryEntry, MemoryType

__all__ = [
    "MemoryStore",
    "MemoryEntry",
    "MemoryType",
]
