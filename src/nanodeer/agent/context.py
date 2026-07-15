"""Read-only functions that build one ephemeral turn context."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from nanodeer.agent.messages import HumanMessage
from nanodeer.agent.state import AgentState
from nanodeer.workspace import Workspace, WorkspacePathError

logger = logging.getLogger(__name__)

_TEXT_EXTENSIONS = frozenset({
    ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".conf", ".log", ".py", ".js", ".ts", ".jsx", ".tsx", ".html",
    ".htm", ".css", ".scss", ".sass", ".less", ".sh", ".bash", ".zsh",
    ".env", ".gitignore", ".dockerfile",
})

_TEXT_MIME_PREFIXES = (
    "text/", "application/json", "application/javascript",
    "application/xml", "application/yaml", "application/toml",
)


@dataclass
class ContextView:
    """Ephemeral inputs assembled for one model turn."""

    memory_context: str | None = None
    plan_context: str | None = None
    events: list = field(default_factory=list)
    uploaded_files_list: str | None = None
    uploaded_files: list[dict] | None = None


def _last_user_message(state: AgentState) -> str:
    for message in reversed(state.messages):
        if isinstance(message, HumanMessage):
            return message.content if isinstance(message.content, str) else str(message.content or "")
    return ""


async def save_uploaded_files(workspace: Workspace, uploaded_files: list[dict] | None) -> None:
    """Persist request uploads at the workspace boundary."""
    for uploaded in uploaded_files or []:
        name = str(uploaded.get("name", "unnamed")) or "unnamed"
        content = uploaded.get("content", b"")
        mime_type = uploaded.get("mime_type", "")
        try:
            destination = workspace.upload_target(name)
        except WorkspacePathError:
            logger.warning("Rejected unsafe upload name: %r", name)
            continue

        extension = destination.suffix.lower()
        is_text = mime_type.startswith(_TEXT_MIME_PREFIXES) or extension in _TEXT_EXTENSIONS
        if is_text:
            try:
                text = content.decode("utf-8") if isinstance(content, bytes) else content
                destination.write_text(text, encoding="utf-8")
                continue
            except (UnicodeDecodeError, UnicodeError):
                pass
        data = content if isinstance(content, bytes) else content.encode()
        destination.write_bytes(data)


def uploaded_files_context(workspace: Workspace) -> str | None:
    """Return the stable virtual upload listing visible to the model."""
    upload_root = workspace.uploads
    if not upload_root.exists():
        return None
    files = sorted(path for path in upload_root.iterdir() if not path.is_symlink())
    if not files:
        return None
    lines = []
    for path in files:
        size = path.stat().st_size if path.is_file() else 0
        size_label = f" ({size} bytes)" if size else ""
        lines.append(f"- {path.name} -> /uploads/{path.name}{size_label}")
    return "\n".join(lines)


async def transform_context(
    state: AgentState,
    signals: ContextView,
    *,
    memory_store,
    workspace: Workspace,
) -> None:
    """Populate ephemeral model context without replacing or persisting State."""
    context_hint = _last_user_message(state) or None
    signals.memory_context = memory_store.load_for_prompt(context_hint=context_hint)
    signals.uploaded_files_list = uploaded_files_context(workspace)


__all__ = [
    "ContextView",
    "save_uploaded_files",
    "transform_context",
    "uploaded_files_context",
]
