"""Web fetch tool - retrieve and clean content from a URL."""

import re
import urllib.error
import urllib.request

from langchain_core.tools import tool


@tool
def fetch_url(url: str, timeout: int = 10) -> str:
    """Fetch the content of a web page and extract clean text.

    Sends an HTTP GET request to the URL, removes scripts/styles/navigation,
    and returns clean readable text.

    Args:
        url: The full URL to fetch (must start with http:// or https://).
        timeout: Request timeout in seconds (default 10, max 30).

    Returns:
        Cleaned page text (first 300 lines), or error message.
    """
    if not url:
        return "Error: URL is required"

    if not url.startswith(("http://", "https://")):
        return f"Error: Invalid URL scheme. Must start with http:// or https://. Got: {url}"

    timeout = max(1, min(30, timeout))

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Nanodeer/1.0; +http://nanodeer.ai)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(req, timeout=timeout)
        html = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return f"Failed to reach server: {e.reason}"
    except Exception as e:
        return f"Error: {str(e)}"

    # Remove script, style, nav, footer, header sections
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<noscript[^>]*>.*?</noscript>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<select[^>]*>.*?</select>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<textarea[^>]*>.*?</textarea>', '', html, flags=re.DOTALL | re.IGNORECASE)

    # Replace block elements with newlines
    html = re.sub(r'</(p|div|br|h[1-6]|li|tr)>', '\n', html, flags=re.IGNORECASE)

    # Remove all HTML tags
    text = re.sub(r'<[^>]+>', '', html)

    # Decode HTML entities
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&amp;', '&')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    text = text.replace('\xa0', ' ')

    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\n+', '\n\n', text)

    # Take first 300 lines
    lines = text.split('\n')
    clean_lines = [line.strip() for line in lines[:300] if line.strip()]

    return '\n'.join(clean_lines) or "(no content)"
