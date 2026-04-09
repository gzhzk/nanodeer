"""Web search tool - search the web using DuckDuckGo HTML."""

import subprocess


def _run_python(python_code: str, timeout: int = 30) -> tuple[int, str, str]:
    """Execute inline Python and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["python3", "-c", python_code],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def web_search_impl(query: str, num_results: int = 5) -> str:
    """Perform web search using DuckDuckGo HTML.

    Works without sandbox — uses Python subprocess + urllib + bs4.

    Args:
        query: Search query string.
        num_results: Number of results (default 5, max 10).

    Returns:
        Formatted search results with titles, URLs, and descriptions.
    """
    if not query or not query.strip():
        return "Error: search query cannot be empty"

    num_results = max(1, min(10, num_results))

    code = f"""
import urllib.parse, urllib.request, urllib.error, sys

query = {repr(query)}
num_results = {num_results}

# Build DuckDuckGo HTML search URL
params = urllib.parse.urlencode({{"q": query, "kl": "us-en"}})
url = "https://html.duckduckgo.com/html/?" + params

headers = {{
    "User-Agent": "Mozilla/5.0 (compatible; Nanodeer/1.0)",
    "Accept": "text/html",
}}
req = urllib.request.Request(url, headers=headers)

try:
    response = urllib.request.urlopen(req, timeout=15)
    html = response.read().decode("utf-8", errors="replace")
except urllib.error.HTTPError as e:
    print(f"HTTP error: e.code {{e.reason}}")
    sys.exit(1)
except urllib.error.URLError as e:
    print(f"URL error: {{e.reason}}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {{str(e)}}")
    sys.exit(1)

# Simple HTML parsing without bs4 dependency
import re

results = []
seen = set()

# Find result links and titles
# Pattern: <a class="result__a" href="...">Title</a>
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

print(f"Search results for: {{query}}")
print(f"({{len(results)}} results found)")
print()
for i, (title, href) in enumerate(results):
    print(f"{{i+1}}. {{title}}")
    print(f"   URL: {{href}}")
    print()
"""
    returncode, stdout, stderr = _run_python(code, timeout=30)

    if returncode != 0:
        return f"Search failed: {stderr or 'unknown error'}"

    if not stdout.strip():
        return f"No results found for: {query}"

    return stdout.strip()


# ============================================================================
# LangChain tool wrapper
# ============================================================================

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
    return web_search_impl(query, num_results)
