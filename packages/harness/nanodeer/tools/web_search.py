"""Web search tool using DuckDuckGo HTML."""

import re
import urllib.error
import urllib.parse
import urllib.request

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

    num_results = max(1, min(10, num_results))

    params = urllib.parse.urlencode({"q": query, "kl": "us-en"})
    url = "https://html.duckduckgo.com/html/?" + params

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Nanodeer/1.0)",
        "Accept": "text/html",
    }
    req = urllib.request.Request(url, headers=headers)

    try:
        response = urllib.request.urlopen(req, timeout=15)
        html = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return f"HTTP error: {e.code} {e.reason}"
    except urllib.error.URLError as e:
        return f"URL error: {e.reason}"
    except Exception as e:
        return f"Error: {str(e)}"

    results = []
    seen = set()

    links = re.findall(r'<a class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', html)
    titles_text = re.findall(r'<a class="result__a"[^>]*href="[^"]+"[^>]*>([^<]+)</a>', html)

    for i, (href, title) in enumerate(zip(links, titles_text)):
        if i >= num_results:
            break
        title = title.strip()
        href = href.strip()
        if title and title not in seen:
            seen.add(title)
            results.append((title, href))

    if not results:
        return f"No results found for: {query}"

    lines = [f"Search results for: {query}", f"({len(results)} results found)", ""]
    for i, (title, href) in enumerate(results):
        lines.append(f"{i+1}. {title}")
        lines.append(f"   URL: {href}")
        lines.append("")
    return "\n".join(lines)
