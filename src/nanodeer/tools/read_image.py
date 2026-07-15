"""Image understanding tool - read local image file and return base64 for vision analysis.

Reads from local filesystem (user uploads), not from sandbox container.
"""

import base64

from langchain_core.tools import tool

from nanodeer.workspace import WorkspacePathError, resolve_workspace_path


@tool
def read_image(image_path: str, description_request: str = "Describe this image in detail.") -> str:
    """Read an image file for vision-based understanding.

    Reads the image file from the local filesystem, returns its base64-encoded
    content along with a description prompt. The result can be submitted to a
    vision-capable LLM (Claude 3, GPT-4V, etc.) for analysis.

    Args:
        image_path: Workspace path such as /uploads/image.png.
        description_request: What to ask the vision model about the image.
            Examples:
            - "Describe this image in detail."
            - "What text is in this image?"
            - "Extract all data from this chart."

    Returns:
        Base64-encoded image data with the description request, or error.
    """
    if not image_path:
        return "Error: image_path is required"

    try:
        resolved = resolve_workspace_path(image_path, access="read")
    except WorkspacePathError as e:
        return f"Error: access denied for {image_path}: {e}"

    if not resolved.exists():
        return f"Error: image file not found: {image_path}"

    if not resolved.is_file():
        return f"Error: not a file: {image_path}"

    # Check file size (max 10MB)
    size = resolved.stat().st_size
    if size > 10 * 1024 * 1024:
        return f"Error: image file too large ({size / 1024 / 1024:.1f}MB, max 10MB)"

    # Check extension
    ext = resolved.suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
        return f"Error: unsupported image format: {ext}. Supported: jpg, png, gif, webp, bmp"

    try:
        with resolved.open("rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception as e:
        return f"Error reading image: {str(e)}"

    return (
        f"[IMAGE_DATA_START]\n"
        f"{img_b64}\n"
        f"[IMAGE_DATA_END]\n"
        f"[REQUEST:] {description_request}\n"
        f"[SIZE:] {size} bytes ({size/1024:.1f}KB)\n"
        f"[FORMAT:] {ext.lstrip('.')}"
    )
