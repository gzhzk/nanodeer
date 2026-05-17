"""Web search tool using duckduckgo_search library."""

import logging
import time

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None  # type: ignore[assignment]


@tool
def web_search(query: str, num_results: int = 5) -> str:
    """Search the web for information.

    Uses DuckDuckGo search via the duckduckgo_search library.
    Returns titles, URLs, and descriptions for each result.

    Args:
        query: The search query string.
        num_results: Number of results to return (default 5, max 10).

    Returns:
        Search results with titles, URLs, and descriptions.
    """
    t0 = time.monotonic()
    if not query or not query.strip():
        return "Error: search query cannot be empty"

    num_results = max(1, min(10, num_results))

    if DDGS is None:
        return "Error: duckduckgo_search not installed. Run: pip install duckduckgo-search"

    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=num_results))
    except Exception as e:
        return f"Search error: {str(e)}"

    results = []
    seen = set()
    for r in raw:
        title = r.get("title", "").strip()
        href = r.get("href", "").strip()
        snippet = r.get("body", "").strip()
        if title and href and title not in seen:
            seen.add(title)
            results.append((title, href, snippet))

    if not results:
        logger.info("query=%s results=0 duration=%.2fs", query, time.monotonic() - t0)
        return f"No results found for: {query}"

    logger.info("query=%s results=%d duration=%.2fs", query, len(results), time.monotonic() - t0)

    lines = [f"Search results for: {query}", f"({len(results)} results found)", ""]
    for i, (title, href, snippet) in enumerate(results):
        lines.append(f"{i+1}. {title}")
        lines.append(f"   URL: {href}")
        if snippet:
            lines.append(f"   {snippet}")
        lines.append("")
    return "\n".join(lines)
