"""Web fetch tool - retrieve content from a URL.

Security: URL is validated and passed via base64 encoding to prevent injection.
HTML is parsed and cleaned (scripts/styles removed) to extract readable text.
"""

from langchain_core.tools import tool


@tool
def fetch_url(url: str, timeout: int = 10) -> str:
    """Fetch the content of a web page and extract clean text.

    Sends an HTTP GET request to the URL, parses the HTML, removes
    script/style/nav/footer elements, and returns clean text content.

    Args:
        url: The full URL to fetch (must start with http:// or https://).
        timeout: Request timeout in seconds (default 10, max 30).

    Returns:
        Cleaned page text (first 500 lines), or error message.
    """
    # Validation only - actual execution happens in sandbox via _execute_in_sandbox
    if not url.startswith(("http://", "https://")):
        return f"Error: Invalid URL scheme. Must start with http:// or https://. Got: {url}"
    if timeout < 1:
        return "Error: timeout must be at least 1 second"
    return f"[Fetching {url}...]"
