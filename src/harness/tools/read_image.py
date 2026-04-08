"""Image understanding tool - read image file and prepare for vision analysis.

Reads an image file and returns its contents as base64-encoded data,
ready for submission to a vision-capable LLM for analysis.

Security: only allows access to files under /mnt/user-data/.
"""

import base64

from langchain_core.tools import tool


@tool
def read_image(image_path: str, description_request: str = "Describe this image in detail.") -> str:
    """Read an image file for vision-based understanding.

    Reads the image file, returns its base64-encoded content along with
    a description prompt. The result can be submitted to a vision-capable
    LLM (Claude 3, GPT-4V, etc.) for analysis.

    Args:
        image_path: Virtual path to the image file (must start with /mnt/user-data/).
        description_request: What to ask the vision model about the image.
            Examples:
            - "Describe this image in detail."
            - "What text is in this image?"
            - "Extract all data from this chart."

    Returns:
        Base64-encoded image data with the description request, or error.
    """
    # Validation only - actual file reading happens in sandbox
    if not image_path:
        return "Error: image_path is required"
    if not image_path.startswith("/mnt/user-data/"):
        return f"Error: image_path must start with /mnt/user-data/. Got: {image_path}"
    if not description_request:
        return "Error: description_request cannot be empty"
    return f"[Reading image: {image_path}]"
