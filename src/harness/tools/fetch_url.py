"""Web fetch tool - retrieve and clean content from a URL.

Works without sandbox — uses Python urllib to fetch and clean HTML.
"""

import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request


def fetch_url_impl(url: str, timeout: int = 10) -> str:
    """Fetch URL and extract clean text content.

    Works without sandbox — uses Python subprocess + urllib + regex.

    Args:
        url: Full URL to fetch.
        timeout: Request timeout in seconds (default 10, max 30).

    Returns:
        Cleaned page text, or error message.
    """
    if not url:
        return "Error: URL is required"

    if not url.startswith(("http://", "https://")):
        return f"Error: Invalid URL scheme. Must start with http:// or https://. Got: {url}"

    timeout = max(1, min(30, timeout))

    code = f"""
import urllib.request, urllib.error, re, sys

url = {repr(url)}
timeout = {timeout}

headers = {{
    "User-Agent": "Mozilla/5.0 (compatible; Nanodeer/1.0; +http://nanodeer.ai)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}}

try:
    req = urllib.request.Request(url, headers=headers)
    response = urllib.request.urlopen(req, timeout=timeout)
    html = response.read().decode("utf-8", errors="replace")
except urllib.error.HTTPError as e:
    print(f"HTTP {{e.code}}: {{e.reason}}")
    sys.exit(1)
except urllib.error.URLError as e:
    print(f"Failed to reach server: {{e.reason}}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {{str(e)}}")
    sys.exit(1)

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
html = re.sub(r'</(p|div|br|h[1-6]|li|tr)>', '\\\\n', html, flags=re.IGNORECASE)

# Remove all HTML tags
text = re.sub(r'<[^>]+>', '', html)

# Decode HTML entities
text = text.replace('&nbsp;', ' ')
text = text.replace('&lt;', '<')
text = text.replace('&gt;', '>')
text = text.replace('&amp;', '&')
text = text.replace('&quot;', '"')
text = text.replace('&#39;', "'")
text = text.replace('\\xa0', ' ')

# Collapse whitespace
text = re.sub(r'[ \\t]+', ' ', text)
text = re.sub(r'\\n\\n+', '\\\\n\\\\n', text)

# Take first 300 lines
lines = text.split('\\\\n')
clean_lines = []
for line in lines[:300]:
    line = line.strip()
    if line:
        clean_lines.append(line)

print('\\\\n'.join(clean_lines))
"""
    result = subprocess.run(
        ["python3", "-c", code],
        capture_output=True,
        text=True,
        timeout=timeout + 5,
    )

    if result.returncode != 0:
        return f"Fetch failed: {result.stderr.strip() or 'unknown error'}"

    return result.stdout.strip() or "(no content)"


# ============================================================================
# LangChain tool wrapper
# ============================================================================

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
    return fetch_url_impl(url, timeout)
