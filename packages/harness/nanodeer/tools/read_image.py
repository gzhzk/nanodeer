"""Image understanding tool - read image file and return base64 for vision analysis.

Works without sandbox — reads local file, base64-encodes, and formats
for submission to a vision-capable LLM.
"""

import base64
import os
import re


def read_image_impl(image_path: str, description_request: str = "Describe this image in detail.") -> str:
    """Read an image file and return base64-encoded data.

    Works without sandbox — reads from filesystem directly.

    Supports both virtual paths (/mnt/user-data/...) and absolute paths.

    Args:
        image_path: Path to the image file.
        description_request: What to ask the vision model.

    Returns:
        Base64-encoded image data with description request, or error.
    """
    if not image_path:
        return "Error: image_path is required"

    if not description_request:
        return "Error: description_request cannot be empty"

    # Resolve the actual filesystem path
    if image_path.startswith("/mnt/user-data/"):
        # Virtual path: translate to physical workspace path
        # Default workspace is /workspace/{thread_id} inside container
        # For local execution without container, try uploads dir first
        relative = image_path[len("/mnt/user-data/"):].lstrip("/")

        # Try workspace path
        workspace_path = os.path.join("/workspace", relative)
        if os.path.exists(workspace_path):
            actual_path = workspace_path
        else:
            # Fallback: try tmp nanodeer uploads
            upload_path = os.path.join("/tmp/nanodeer/uploads", relative)
            if os.path.exists(upload_path):
                actual_path = upload_path
            else:
                actual_path = workspace_path  # return error below
    else:
        # Absolute path — use directly
        actual_path = image_path

    if not os.path.exists(actual_path):
        return f"Error: image file not found: {image_path}"

    if not os.path.isfile(actual_path):
        return f"Error: not a file: {image_path}"

    # Check file size (max 10MB)
    size = os.path.getsize(actual_path)
    if size > 10 * 1024 * 1024:
        return f"Error: image file too large ({size / 1024 / 1024:.1f}MB, max 10MB)"

    # Check extension
    ext = os.path.splitext(actual_path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
        return f"Error: unsupported image format: {ext}. Supported: jpg, png, gif, webp, bmp"

    try:
        with open(actual_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception as e:
        return f"Error reading image: {str(e)}"

    # Format output for vision model
    return (
        f"[IMAGE_DATA_START]\n"
        f"{img_b64}\n"
        f"[IMAGE_DATA_END]\n"
        f"[REQUEST:] {description_request}\n"
        f"[SIZE:] {size} bytes ({size/1024:.1f}KB)\n"
        f"[FORMAT:] {ext.lstrip('.')}"
    )


# ============================================================================
# LangChain tool wrapper
# ============================================================================

from langchain_core.tools import tool


@tool
def read_image(image_path: str, description_request: str = "Describe this image in detail.") -> str:
    """Read an image file for vision-based understanding.

    Reads the image file, returns its base64-encoded content along with
    a description prompt. The result can be submitted to a vision-capable
    LLM (Claude 3, GPT-4V, etc.) for analysis.

    Args:
        image_path: Virtual or absolute path to the image file.
            For virtual paths: must start with /mnt/user-data/.
        description_request: What to ask the vision model about the image.
            Examples:
            - "Describe this image in detail."
            - "What text is in this image?"
            - "Extract all data from this chart."

    Returns:
        Base64-encoded image data with the description request, or error.
    """
    return read_image_impl(image_path, description_request)
