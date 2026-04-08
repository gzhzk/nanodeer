"""File read/write tools inside sandbox.

Security: all paths must start with /mnt/user-data/.
Content is base64-encoded to avoid shell injection.
"""

import base64

from langchain_core.tools import tool


@tool
def read_file(file_path: str) -> str:
    """Read content from a file inside the sandbox.

    Args:
        file_path: Virtual path to the file (must start with /mnt/user-data/).

    Returns:
        File content as string, or error message.
    """
    import subprocess
    result = subprocess.run(
        ["cat", file_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return f"Error: {result.stderr}"
    return result.stdout


@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file inside the sandbox.

    Content is base64-encoded before passing to avoid shell injection.

    Args:
        file_path: Virtual path to the file (must start with /mnt/user-data/).
        content: Content to write.

    Returns:
        Success message or error.
    """
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    result = subprocess.run(
        ["python3", "-c", f"import base64; open('{file_path}', 'wb').write(base64.b64decode('{encoded}'))"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return f"Error: {result.stderr}"
    return f"Written to {file_path}"
