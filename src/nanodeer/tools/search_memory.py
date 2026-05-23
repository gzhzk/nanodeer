"""search_memory tool — search and read saved wiki entries and memories."""

from langchain_core.tools import tool

from ..agent.memory.storage import MemoryStore


@tool
def search_memory(query: str = "", max_results: int = 10) -> str:
    """Search saved wiki entries and memories by keyword.

    Use this to find relevant information from past conversations before
    answering. Returns matching entries with their paths, summaries, and
    full content (truncated if long). If query is empty, returns the most
    recent entries.

    For wiki entries, the path can be used to reference the source.
    Example: "wiki/project/language" for a project language decision.

    Args:
        query: Search keywords. Leave empty to list recent entries.
        max_results: Maximum entries to return (default 10, max 20).

    Returns:
        Formatted memory entries with path and content.
    """
    store = MemoryStore()
    results = store.search_wiki(query=query, max_entries=max(min(max_results, 20), 1))

    if not results:
        return "No matching wiki entries found."

    lines = []
    for entry in results:
        tag_str = f" [{', '.join(entry.tags)}]" if entry.tags else ""
        content = entry.content
        if len(content) > 1000:
            content = content[:1000] + "\n... [truncated]"
        lines.append(
            f"## {entry.path}{tag_str}\n"
            f"*{entry.summary}*\n\n"
            f"{content}"
        )

    return "\n\n---\n\n".join(lines)
