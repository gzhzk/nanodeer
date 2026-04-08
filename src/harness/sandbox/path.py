"""Virtual path translation and security validation.

Agent sees files through /mnt/user-data/ virtual paths.
These are translated to physical paths inside the Docker container.
"""
import os
import re


VIRTUAL_PREFIX = "/mnt/user-data"
WORKSPACE_ROOT = "/workspace"


def virtual2physical(virtual_path: str, thread_id: str) -> str:
    """Translate virtual path to physical path inside container.

    /mnt/user-data/workspace/file.py -> /workspace/{thread_id}/workspace/file.py
    """
    if not virtual_path.startswith(VIRTUAL_PREFIX):
        raise ValueError(f"Path must start with {VIRTUAL_PREFIX}: {virtual_path}")

    relative = virtual_path[len(VIRTUAL_PREFIX):].lstrip("/")
    return os.path.join(WORKSPACE_ROOT, thread_id, relative)


def validate_path(virtual_path: str) -> str | None:
    """Validate and sanitize virtual path. Returns None if dangerous.

    Blocks: path traversal (../), system files (/etc/passwd, /root/.ssh).
    """
    # Check for .. BEFORE normpath - normpath resolves .. first, bypassing checks
    # Reject any path containing .. components (we only need direct subdirectories)
    if ".." in virtual_path:
        return None

    normalized = os.path.normpath(virtual_path)

    if not normalized.startswith(VIRTUAL_PREFIX):
        return None

    # Block dangerous paths after normpath resolution
    dangerous = [r"^/etc/passwd$", r"^/etc/shadow$", r"^/root/\.ssh/"]
    for pattern in dangerous:
        if re.match(pattern, normalized):
            return None

    return normalized


def translate_and_validate(virtual_path: str, thread_id: str) -> str:
    """Validate then translate virtual path to physical path."""
    validated = validate_path(virtual_path)
    if validated is None:
        raise ValueError(f"Invalid or dangerous path: {virtual_path}")
    return virtual2physical(validated, thread_id)
