"""search_memory tool — read and search USER.md / MEMORY.md flat files."""

from langchain_core.tools import tool

from ..agent.memory.storage import MemoryStore


@tool
def search_memory(query: str = "") -> str:
    """Search saved memory (USER.md and MEMORY.md) by keyword.

    Use this to find relevant information from past conversations and
    persisted knowledge. If query is empty, returns all content.

    Args:
        query: Search keywords (case-insensitive). Leave empty to show all.

    Returns:
        Matching memory content, or a message if nothing is found.
    """
    store = MemoryStore()
    q = query.strip().lower()
    results = []

    memory = store.load_memory()
    if memory:
        if not q or q in memory.lower():
            label = "## MEMORY.md — long-term knowledge\n\n"
            preview = memory[:2000] + "\n... [truncated]" if len(memory) > 2000 else memory
            results.append(label + preview)

    user = store.load_user_memory()
    if user:
        if not q or q in user.lower():
            label = "\n\n## USER.md — user preferences\n\n"
            preview = user[:2000] + "\n... [truncated]" if len(user) > 2000 else user
            results.append(label + preview)

    if not results:
        return "No matching memory entries found."

    return "".join(results)
