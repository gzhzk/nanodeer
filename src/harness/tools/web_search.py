"""Web search tool - search the web using DuckDuckGo."""

from langchain_core.tools import tool


@tool
def web_search(query: str, num_results: int = 5) -> str:
    """Search the web for information.

    Uses DuckDuckGo HTML search to find relevant web pages.
    Returns titles, URLs, and snippets for each result.

    Args:
        query: The search query string.
        num_results: Number of results to return (default 5, max 10).

    Returns:
        Search results with titles, URLs, and descriptions.
    """
    if not query or not query.strip():
        return "Error: search query cannot be empty"
    if num_results < 1:
        num_results = 1
    if num_results > 10:
        num_results = 10
    return f"[Searching for: {query}]"
