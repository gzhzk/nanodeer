"""Thread-bound virtual workspace and path security boundary.

The agent sees stable logical paths while host-side file tools operate on a
thread-specific physical directory.  Sandbox/container execution is optional:
both local tools and execution backends share the same workspace layout.
"""

from __future__ import annotations

import hashlib
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Iterator
from urllib.parse import unquote


class WorkspaceAccess(str, Enum):
    READ = "read"
    WRITE = "write"


class WorkspacePathError(ValueError):
    """Raised when a logical path escapes its allowed workspace boundary."""


def safe_thread_key(thread_id: str) -> str:
    """Return a collision-resistant filesystem key for an arbitrary thread ID."""
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", thread_id):
        return thread_id
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", thread_id).strip("-_")[:72]
    slug = slug or "thread"
    digest = hashlib.sha256(thread_id.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"{slug}-{digest}"


def _contains_traversal(path: str) -> bool:
    """Detect traversal before any path normalization can hide it."""
    candidates = (path, unquote(path))
    for candidate in candidates:
        normalized = candidate.replace("\\", "/")
        if any(part == ".." for part in normalized.split("/")):
            return True
    return False


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class Workspace:
    """One persistent thread workspace with stable virtual mount points."""

    thread_id: str
    root: Path
    host_read_roots: tuple[Path, ...] = ()

    @property
    def files(self) -> Path:
        return self.root / "workspace"

    @property
    def uploads(self) -> Path:
        return self.root / "uploads"

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    def ensure(self) -> "Workspace":
        """Create the persistent thread layout and return this workspace."""
        if self.root.exists() and self.root.is_symlink():
            raise WorkspacePathError(f"workspace root cannot be a symlink: {self.root}")
        self.root.mkdir(parents=True, exist_ok=True)
        for directory in (self.files, self.uploads, self.outputs):
            if directory.exists() and directory.is_symlink():
                raise WorkspacePathError(
                    f"workspace mount cannot be a symlink: {directory}"
                )
            directory.mkdir(parents=True, exist_ok=True)
        return self

    def resolve(
        self,
        logical_path: str,
        *,
        access: WorkspaceAccess | str = WorkspaceAccess.READ,
    ) -> Path:
        """Resolve a logical path under the correct access policy.

        Canonical mounts:
          /workspace  -> persistent working files (read/write)
          /uploads    -> user uploads (read-only to agent tools)
          /outputs    -> produced artifacts (read/write)

        `/mnt/user-data` remains a compatibility alias for one release cycle.
        Relative paths resolve beneath `/workspace`.  Explicit host paths are
        read-only and must be beneath a configured host read root.
        """
        if not isinstance(logical_path, str) or not logical_path or "\x00" in logical_path:
            raise WorkspacePathError("path is empty or contains a NUL byte")
        if _contains_traversal(logical_path):
            raise WorkspacePathError(f"path traversal is not allowed: {logical_path!r}")

        requested_access = WorkspaceAccess(access)
        normalized = logical_path.replace("\\", "/")

        mount = self._match_mount(normalized)
        if mount is not None:
            virtual_root, physical_root, relative, writable = mount
            if requested_access == WorkspaceAccess.WRITE and not writable:
                raise WorkspacePathError(f"virtual mount is read-only: {virtual_root}")
            return self._resolve_beneath(physical_root, relative)

        if normalized.startswith("/"):
            if requested_access == WorkspaceAccess.WRITE:
                raise WorkspacePathError("host paths are read-only")
            return self._resolve_host_read(Path(normalized))

        relative = PurePosixPath(normalized)
        if relative.is_absolute():
            raise WorkspacePathError(f"unsupported path: {logical_path!r}")
        return self._resolve_beneath(self.files, relative.as_posix())

    def to_virtual(self, physical_path: str | Path) -> str:
        """Convert a physical workspace path back to its canonical logical path."""
        resolved = Path(physical_path).resolve(strict=False)
        mounts = (
            (self.files.resolve(), "/workspace"),
            (self.uploads.resolve(), "/uploads"),
            (self.outputs.resolve(), "/outputs"),
        )
        for root, virtual_root in mounts:
            if resolved == root:
                return virtual_root
            if _is_relative_to(resolved, root):
                return f"{virtual_root}/{resolved.relative_to(root).as_posix()}"
        raise WorkspacePathError(f"path is outside workspace: {physical_path}")

    def upload_target(self, name: str) -> Path:
        """Resolve a sanitized upload name for trusted API ingestion."""
        normalized = name.replace("\\", "/")
        basename = PurePosixPath(normalized).name
        if not basename or basename in (".", "..") or basename != normalized:
            raise WorkspacePathError(f"invalid upload name: {name!r}")
        return self._resolve_beneath(self.uploads, basename)

    def _match_mount(
        self,
        path: str,
    ) -> tuple[str, Path, str, bool] | None:
        mounts = (
            ("/workspace", self.files, True),
            ("/uploads", self.uploads, False),
            ("/outputs", self.outputs, True),
            ("/mnt/user-data", self.root, True),
        )
        for virtual_root, physical_root, writable in mounts:
            if path == virtual_root:
                return virtual_root, physical_root, ".", writable
            prefix = virtual_root + "/"
            if path.startswith(prefix):
                relative = path[len(prefix):]
                if (
                    virtual_root == "/mnt/user-data"
                    and (relative == "uploads" or relative.startswith("uploads/"))
                ):
                    writable = False
                return virtual_root, physical_root, relative, writable
        return None

    def _resolve_beneath(self, root: Path, relative: str) -> Path:
        root = root.resolve(strict=False)
        candidate = root / Path(relative)
        resolved = candidate.resolve(strict=False)
        if not _is_relative_to(resolved, root) and resolved != root:
            raise WorkspacePathError("resolved path escapes workspace")

        # Reject existing symlink components.  This keeps the pure-Python
        # boundary conservative; an openat2-based backend can relax this later.
        current = root
        for part in Path(relative).parts:
            if part in ("", "."):
                continue
            current = current / part
            if current.exists() and current.is_symlink():
                raise WorkspacePathError(f"symlink paths are not allowed: {current}")
        return resolved

    def _resolve_host_read(self, candidate: Path) -> Path:
        resolved = candidate.expanduser().resolve(strict=False)
        for root in self.host_read_roots:
            allowed = root.expanduser().resolve(strict=False)
            if resolved == allowed or _is_relative_to(resolved, allowed):
                return resolved
        raise WorkspacePathError(f"host path is outside configured read roots: {candidate}")


class WorkspaceManager:
    """Creates deterministic persistent workspaces for conversation threads."""

    def __init__(
        self,
        storage_path: str | Path | None = None,
        *,
        host_read_roots: tuple[str | Path, ...] | None = None,
    ):
        if storage_path is None:
            from nanodeer.config import get_config

            storage_path = get_config().thread.storage_path
        self.storage_path = Path(storage_path).expanduser().resolve(strict=False)

        if host_read_roots is None:
            roots: list[Path] = [Path(__file__).resolve().parents[2]]
            for item in os.getenv("NANODEER_EXTRA_ALLOWED_PATHS", "").split(os.pathsep):
                if item:
                    roots.append(Path(item))
            host_read_roots = tuple(roots)
        self.host_read_roots = tuple(
            Path(root).expanduser().resolve(strict=False) for root in host_read_roots
        )

    def open(self, thread_id: str, *, create: bool = True) -> Workspace:
        key = safe_thread_key(thread_id or "default")
        root = self.storage_path / key / "user-data"
        workspace = Workspace(
            thread_id=thread_id or "default",
            root=root,
            host_read_roots=self.host_read_roots,
        )
        return workspace.ensure() if create else workspace


_current_workspace: ContextVar[Workspace | None] = ContextVar(
    "nanodeer_current_workspace",
    default=None,
)


def get_current_workspace() -> Workspace | None:
    return _current_workspace.get()


def current_workspace_or_default() -> Workspace:
    """Return the active workspace or the legacy default tool scope."""
    return get_current_workspace() or WorkspaceManager().open("default", create=False)


def activate_workspace(workspace: Workspace) -> Token[Workspace | None]:
    """Bind a workspace until the returned token is reset."""
    return _current_workspace.set(workspace)


def reset_workspace(token: Token[Workspace | None]) -> None:
    _current_workspace.reset(token)


@contextmanager
def bind_workspace(workspace: Workspace) -> Iterator[Workspace]:
    """Bind a workspace to the current async/task context."""
    token: Token[Workspace | None] = _current_workspace.set(workspace)
    try:
        yield workspace
    finally:
        _current_workspace.reset(token)


def resolve_workspace_path(
    logical_path: str,
    *,
    access: WorkspaceAccess | str = WorkspaceAccess.READ,
) -> Path:
    """Resolve through the active run workspace, with a default compatibility scope."""
    workspace = current_workspace_or_default()
    return workspace.resolve(logical_path, access=access)
