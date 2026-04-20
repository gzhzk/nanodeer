"""Memory tool - save to USER.md or MEMORY.md."""

from langchain_core.tools import tool

from ..agent.memory.storage import MemoryStore


@tool
def save_memory(content: str, target: str = "memory", mode: str = "append") -> str:
    """Save important information to long-term memory.

    Args:
        content: The information to remember.
        target: "user" for USER.md (preferences/context),
                "memory" for MEMORY.md (facts/knowledge).
                Defaults to "memory".
        mode: "append" (default) adds to existing content below.
              "replace" overwrites entirely — use when rewriting sections.

    Returns:
        Success message.
    """
    store = MemoryStore()

    if target == "user":
        store.save_user_memory(content)
        preview = content[:200] + "..." if len(content) > 200 else content
        return f"User memory saved: {preview}"
    else:
        store.save_memory(content, mode=mode)
        preview = content[:200] + "..." if len(content) > 200 else content
        return f"Memory {'replaced' if mode == 'replace' else 'saved'}: {preview}"
