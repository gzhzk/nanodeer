"""Memory tool - save to USER.md, MEMORY.md, or wiki/entries/."""

import re
from langchain_core.tools import tool

from ..agent.memory.storage import MemoryStore


@tool
def save_memory(
    target: str,
    content: str,
    tags: list[str] | None = None,
    mode: str = "append",
) -> str:
    """Save important information to long-term memory.

    Use this to persist knowledge across conversations. The system supports
    three memory tiers:
      - wiki/<category>/<name> → structured wiki entries (preferred)
      - "memory" → legacy MEMORY.md flat file
      - "user"   → USER.md preferences

    Wiki entries are the recommended way to store structured knowledge. Each
    entry is a standalone page with tags for retrieval. The LLM decides what
    to create, update, and organize — building a personal knowledge base
    over time.

    Args:
        target: Destination for the memory:
                - "wiki/<category>/<name>" → structured wiki entry (recommended).
                  Examples: "wiki/project/language", "wiki/user/coding_style",
                            "wiki/task/current_goal", "wiki/arch/deployment"
                  Use hierarchical paths to organize knowledge.
                - "memory" → MEMORY.md flat file (legacy, append/replace)
                - "user" → USER.md preferences (always replace)
        content: The information to remember. Markdown format recommended.
                 For wiki entries, include structured sections with clear headings.
        tags: Optional list of tags for wiki entries. Used for retrieval.
              Only applies to "wiki/" targets. Example: ["python", "architecture"]
        mode: "append" (default) adds to existing content.
              "replace" overwrites entirely — use when rewriting sections.
              Only applies to "memory" and "user" targets.

    Returns:
        Success message with preview.
    """
    store = MemoryStore()
    preview = content[:200] + "..." if len(content) > 200 else content

    # Wiki entries — structured, indexed, searchable
    if target.startswith("wiki/"):
        path = target.removeprefix("wiki/").strip("/")
        if not path:
            return "Error: wiki path must not be empty (e.g. 'wiki/project/language')"
        store.save_wiki_entry(path, content, tags=tags)
        tag_info = f" tags=[{', '.join(tags)}]" if tags else ""
        return f"Wiki entry saved [{path}]:{tag_info} {preview}"

    # Legacy targets
    if target == "user":
        store.save_user_memory(content)
        return f"User memory saved: {preview}"
    else:
        store.save_memory(content, mode=mode)
        return f"Memory {'replaced' if mode == 'replace' else 'saved'}: {preview}"