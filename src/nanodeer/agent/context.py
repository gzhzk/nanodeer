"""ContextManager — parallel loader of all LLM prompt context.

Replaces ThreadDataMiddleware + FileMiddleware + PlanMiddleware + MemoryMiddleware.before_llm.
Single async load() call that:
  1. Creates thread user-data directories (for sandbox volume mounts)
  2. Writes uploaded files to disk
  3. Loads memory (USER.md / MEMORY.md) and plan context
  4. Injects all into TurnSignals for prompt assembly

All file I/O runs in parallel via asyncio.gather.
"""

import asyncio
import logging
from pathlib import Path

from nanodeer.agent.memory.storage import MemoryStore
from nanodeer.agent.messages import HumanMessage
from nanodeer.agent.state import ThreadState, TurnSignals
from nanodeer.config import get_config

logger = logging.getLogger(__name__)

_TEXT_EXTENSIONS = frozenset({
    ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".conf", ".log", ".py", ".js", ".ts", ".jsx", ".tsx", ".html",
    ".htm", ".css", ".scss", ".sass", ".less", ".sh", ".bash", ".zsh",
    ".env", ".gitignore", ".dockerfile",
})

_TEXT_MIME_PREFIXES = ("text/", "application/json", "application/javascript",
                       "application/xml", "application/yaml", "application/toml")


class ContextManager:
    """Loads everything the LLM prompt needs — in parallel where possible."""

    def __init__(self, memory_store=None, plan_store=None):
        from nanodeer.plan.storage import PlanStore
        self._memory_store = memory_store or MemoryStore()
        self._plan_store = plan_store or PlanStore()
        self._cfg = get_config()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def load(self, state: ThreadState, signals: TurnSignals) -> None:
        """Load all contexts in parallel, writing results into signals.

        Phase 1 — parallel: dirs + memory + plan
        Phase 2 — sequential after dirs: write uploads + scan (fast, no benefit from more parallelism)
        """
        if not state.thread_id:
            return

        dirs_task = asyncio.create_task(self._ensure_dirs(state))
        memory_task = asyncio.create_task(self._load_memory(state, signals))
        plan_task = asyncio.create_task(self._load_plan(signals))

        # Dirs must be ready before uploads (uploads/ must exist —
        # but mkdir(exist_ok=True) makes this safe even without waiting)
        await dirs_task

        if signals._uploaded_files:
            await self._process_uploads(state, signals)
        await self._scan_uploads(state, signals)

        await memory_task
        await plan_task

    # ------------------------------------------------------------------
    # Internal — each is an independent async task
    # ------------------------------------------------------------------

    async def _ensure_dirs(self, state: ThreadState) -> None:
        """Create thread user-data directories for sandbox volume mounts."""
        root = self._cfg.thread.storage_path / state.thread_id / "user-data"
        (root / "workspace").mkdir(parents=True, exist_ok=True)
        (root / "uploads").mkdir(parents=True, exist_ok=True)
        (root / "outputs").mkdir(parents=True, exist_ok=True)

    def _get_last_user_message(self, state: ThreadState) -> str:
        """Extract last user message for wiki memory retrieval."""
        for msg in reversed(state.messages):
            if isinstance(msg, HumanMessage):
                content = msg.content
                return content if isinstance(content, str) else str(content or "")
        return ""

    async def _load_memory(self, state: ThreadState, signals: TurnSignals) -> None:
        """Load USER.md / MEMORY.md context into signals."""
        if not self._memory_store:
            return
        context_hint = self._get_last_user_message(state) or None
        memory_context = self._memory_store.load_for_prompt(context_hint=context_hint)
        if memory_context:
            signals.memory_context = memory_context
        signals.events.append({
            "type": "memory_context",
            "has_memory": bool(memory_context),
        })

    async def _load_plan(self, signals: TurnSignals) -> None:
        """Load plan context into signals."""
        from nanodeer.plan.types import StepStatus

        plans = self._plan_store.list()
        if not plans:
            return

        parts = []
        for plan in plans:
            steps = plan.steps
            pct = plan.progress_pct

            parts.append(f"<plan id=\"{plan.plan_id}\">")
            parts.append(f"<goal>{plan.goal}</goal>")
            if plan.title:
                parts.append(f"<title>{plan.title}</title>")
            if plan.status.value != "drafting":
                parts.append(f"<status>{plan.status.value}</status>")
            if steps:
                parts.append(f"<progress>{plan.completed_count}/{plan.total_count} steps completed ({pct}%)</progress>")

            for step in steps:
                checkbox = {
                    StepStatus.PENDING: "[ ]",
                    StepStatus.IN_PROGRESS: "[*]",
                    StepStatus.COMPLETED: "[x]",
                    StepStatus.BLOCKED: "[!]",
                    StepStatus.FAILED: "[-]",
                }.get(step.status, "[ ]")
                line = f"{checkbox} {step.content}  (id={step.id})"
                if step.dependencies:
                    line += f"  depends: {', '.join(step.dependencies)}"
                if step.assigned_to:
                    line += f"  assigned: {step.assigned_to}"
                parts.append(line)

            parts.append("</plan>")

        signals.plan_context = "\n".join(parts)

    async def _process_uploads(self, state: ThreadState, signals: TurnSignals) -> None:
        """Write uploaded files to disk."""
        root = self._cfg.thread.storage_path / state.thread_id / "user-data" / "uploads"
        root.mkdir(parents=True, exist_ok=True)

        for f in (signals._uploaded_files or []):
            name = f.get("name", "unnamed")
            content = f.get("content", b"")
            mime_type = f.get("mime_type", "")
            dest = root / name

            ext = Path(name).suffix.lower()
            is_text = mime_type.startswith(_TEXT_MIME_PREFIXES) or ext in _TEXT_EXTENSIONS
            if is_text:
                try:
                    text = content.decode("utf-8") if isinstance(content, bytes) else content
                    dest.write_text(text, encoding="utf-8")
                except (UnicodeDecodeError, UnicodeError):
                    dest.write_bytes(content if isinstance(content, bytes) else content.encode())
            else:
                dest.write_bytes(content if isinstance(content, bytes) else content.encode())

    async def _scan_uploads(self, state: ThreadState, signals: TurnSignals) -> None:
        """Scan uploads dir and inject file list into signals."""
        upload_root = self._cfg.thread.storage_path / state.thread_id / "user-data" / "uploads"
        if not upload_root.exists():
            return

        files = sorted(upload_root.iterdir())
        if not files:
            return

        lines = []
        for f in files:
            size = f.stat().st_size if f.is_file() else 0
            lines.append(f"- {f.name}" + (f" ({size} bytes)" if size else ""))

        signals.uploaded_files_list = "\n".join(lines)
