"""Virtual path translation and security validation.

Agent sees files through /mnt/user-data/ virtual paths.
These are translated to physical paths inside the Docker container.
"""
import os
import re
from pathlib import Path


# Virtual path prefix used by Agent
VIRTUAL_PREFIX = "/mnt/user-data"

# Physical workspace root inside container
WORKSPACE_ROOT = "/workspace"


def virtual2physical(virtual_path: str, thread_id: str) -> str:
    """Translate virtual path to physical path inside container.

    Agent path: /mnt/user-data/workspace/code.py
    Physical path: /workspace/{thread_id}/code.py

    Args:
        virtual_path: Agent's virtual path.
        thread_id: Thread identifier for multi-tenant isolation.

    Returns:
        Physical path inside the container.

    Raises:
        ValueError: If virtual_path doesn't start with /mnt/user-data.
    """
    if not virtual_path.startswith(VIRTUAL_PREFIX):
        raise ValueError(
            f"Path must start with {VIRTUAL_PREFIX}: {virtual_path}"
        )

    # /mnt/user-data/workspace/file.py -> /workspace/thread_id/workspace/file.py
    # or /mnt/user-data/uploads/file.py -> /workspace/thread_id/uploads/file.py
    relative = virtual_path[len(VIRTUAL_PREFIX):].lstrip("/")
    return os.path.join(WORKSPACE_ROOT, thread_id, relative)


def validate_path(virtual_path: str) -> str | None:
    """Validate and sanitize a virtual path.

    Prevents path traversal attacks like:
    - /mnt/user-data/../etc/passwd
    - /mnt/user-data/workspace/../../etc/secret

    Args:
        virtual_path: Path to validate.

    Returns:
        Sanitized path if valid, None if dangerous.
    """
    # Normalize the path to resolve ../
    normalized = os.path.normpath(virtual_path)

    # Check for path traversal attempts
    if ".." in normalized:
        return None

    # Must start with virtual prefix
    if not normalized.startswith(VIRTUAL_PREFIX):
        return None

    # Block dangerous patterns
    dangerous_patterns = [
        r"^/mnt/user-data/\.\./",  # ../ after normpath
        r"^/etc/passwd$",
        r"^/etc/shadow$",
        r"^/root/\.ssh/",
    ]

    for pattern in dangerous_patterns:
        if re.match(pattern, normalized):
            return None

    return normalized


def translate_and_validate(virtual_path: str, thread_id: str) -> str:
    """Combined translate + validate.

    Args:
        virtual_path: Agent's virtual path.
        thread_id: Thread identifier.

    Returns:
        Validated physical path.

    Raises:
        ValueError: If path validation fails.
    """
    validated = validate_path(virtual_path)
    if validated is None:
        raise ValueError(f"Invalid or dangerous path: {virtual_path}")

    return virtual2physical(validated, thread_id)
