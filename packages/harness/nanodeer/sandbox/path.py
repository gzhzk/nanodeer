"""Virtual path translation and security validation.

Two categories of paths inside the container:
- /mnt/user-data: mount point (host base_path/{thread_id}/user-data → /mnt/user-data).
  This IS the real path — do NOT translate.
- /workspace/{thread_id}: agent working directory on ephemeral container rootfs.
  Paths here are created by the agent at runtime and need translation.

Agent virtual paths always start with /mnt/user-data/.
"""

import os
import re


VIRTUAL_PREFIX = "/mnt/user-data"


def virtual2physical(virtual_path: str, thread_id: str) -> str:
    """Translate virtual path to real container path.

    /mnt/user-data/... paths: mount point, already real — return as-is.
    /workspace/... paths: ephemeral container rootfs — translate using thread_id.
    """
    if virtual_path.startswith(VIRTUAL_PREFIX):
        # Mount point — already the real path inside the container
        return virtual_path

    # Agent-created working files: translate to ephemeral container rootfs
    if virtual_path.startswith("/workspace/"):
        parts = virtual_path.split("/", 3)  # /workspace/{thread_id}/rest
        if len(parts) >= 4 and parts[2] == thread_id:
            return virtual_path
        if len(parts) >= 4:
            return f"/workspace/{thread_id}/{parts[3]}"

    # Fallback: treat as working directory relative
    return f"/workspace/{thread_id}/{virtual_path.lstrip('/')}"


def validate_path(virtual_path: str) -> str | None:
    """Validate and sanitize virtual path. Returns None if dangerous.

    Blocks: path traversal (../), system files (/etc/passwd, /root/.ssh).
    /mnt/user-data/... and /workspace/... paths are allowed.
    """
    if ".." in virtual_path:
        return None

    normalized = os.path.normpath(virtual_path)

    # Must be either a mount point path or workspace path
    if not (normalized.startswith(VIRTUAL_PREFIX) or normalized.startswith("/workspace/")):
        return None

    # Block dangerous system paths after normpath resolution
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
