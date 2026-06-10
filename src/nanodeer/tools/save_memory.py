"""Memory tool — save to USER.md or MEMORY.md flat files."""

from langchain_core.tools import tool

from ..agent.memory.storage import MemoryStore


@tool
def save_memory(
    target: str,
    content: str,
    mode: str = "append",
) -> str:
    """Save important information to long-term memory.

    Use this to persist knowledge across conversations. Two targets:

      - "memory" → MEMORY.md flat file (general knowledge, facts)
      - "user"   → USER.md preferences (always replaces)

    The content is included in the system prompt on future conversations,
    so the LLM can recall it without needing to search.

    Args:
        target: "memory" for MEMORY.md (general knowledge, append by default)
                or "user" for USER.md (preferences, always replaces).
        content: The information to remember. Markdown format recommended.
        mode: "append" (default) adds to existing content.
              "replace" overwrites entirely — use when rewriting sections.
              Only applies to "memory" target. "user" always replaces.

    Returns:
        Success message with preview.
    """
    store = MemoryStore()
    preview = content[:200] + "..." if len(content) > 200 else content

    if target == "user":
        store.save_user_memory(content)
        return f"User memory saved: {preview}"
    else:
        store.save_memory(content, mode=mode)
        action = "replaced" if mode == "replace" else "saved"
        return f"Memory {action}: {preview}"
