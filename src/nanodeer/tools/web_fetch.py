"""Fetch a URL and return its content as plain text."""

import logging
import time

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def web_fetch(url: str) -> str:
    """Fetch a web page and return its visible text content.

    Use when search snippets aren't enough — this actually opens the page.
    Returns up to 8000 characters of extracted text.

    Args:
        url: The full URL to fetch (including https://).

    Returns:
        Page text content or error message.
    """
    t0 = time.monotonic()
    if not url or not url.startswith(("http://", "https://")):
        return "Error: URL must start with http:// or https://"

    try:
        import httpx
        resp = httpx.get(url, follow_redirects=True, timeout=15.0)
        resp.raise_for_status()
    except Exception as e:
        logger.warning("fetch url=%s error=%s duration=%.2fs", url, e, time.monotonic() - t0)
        return f"Error fetching URL: {e}"

    content_type = resp.headers.get("content-type", "")
    if "html" in content_type:
        text = _extract_text(resp.text)
    else:
        text = resp.text[:10000]

    logger.info("fetch url=%s chars=%d duration=%.2fs", url, len(text), time.monotonic() - t0)
    return text[:8000] or "(empty page)"


def _extract_text(html: str) -> str:
    """Strip HTML tags and return visible text."""
    import re
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'</?(?:div|p|br|li|h[1-6]|tr|td|th|blockquote|pre)[^>]*>', '\n', html, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', html)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' ')
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()
