"""Persistent storage for threads, uploads, and schedules (JSON files)."""

import json
import uuid
from datetime import datetime
from pathlib import Path

from .config import get_app_config


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


class UploadStorage:
    """Stores user-uploaded files in a temp directory.

    Files are keyed by upload_id (UUID). Each upload_id directory contains
    the raw files. This is ephemeral — cleaned up after the run completes.
    """

    def __init__(self, base_dir: Path | None = None):
        cfg = get_app_config()
        self.base_dir = base_dir or cfg.upload_dir

    def save(self, filename: str, content: bytes) -> str:
        """Save uploaded file content and return an upload_id.

        The upload_id directory holds one or more files.
        """
        upload_id = uuid.uuid4().hex
        upload_dir = self.base_dir / upload_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        safe_name = Path(filename).name
        (upload_dir / safe_name).write_bytes(content)
        metadata = {
            "upload_id": upload_id,
            "filename": safe_name,
            "size_bytes": len(content),
            "created_at": datetime.utcnow().isoformat(),
        }
        (upload_dir / "_meta.json").write_text(json.dumps(metadata, indent=2))
        return upload_id

    def get(self, upload_id: str) -> dict | None:
        """Load metadata for an upload."""
        meta_file = self.base_dir / upload_id / "_meta.json"
        if not meta_file.exists():
            return None
        return json.loads(meta_file.read_text())

    def list_files(self, upload_id: str) -> list[Path]:
        """List all files (excluding metadata) in an upload directory."""
        d = self.base_dir / upload_id
        if not d.exists():
            return []
        return [f for f in d.iterdir() if f.name != "_meta.json"]

    def delete(self, upload_id: str) -> None:
        """Delete an upload and all its files."""
        import shutil

        d = self.base_dir / upload_id
        if d.exists():
            shutil.rmtree(d)


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------


class ScheduleStorage:
    """CRUD for scheduled jobs, stored as one JSON file per job."""

    def __init__(self, base_dir: Path | None = None):
        cfg = get_app_config()
        self.base_dir = base_dir or cfg.schedule_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        return self.base_dir / f"{job_id}.json"

    def create(self, name: str, prompt: str, cron: str, thread_id: str | None) -> dict:
        """Create a new schedule and persist it."""
        job_id = uuid.uuid4().hex
        now = datetime.utcnow()
        entry = {
            "id": job_id,
            "name": name,
            "prompt": prompt,
            "cron": cron,
            "thread_id": thread_id,
            "enabled": True,
            "created_at": now.isoformat(),
            "last_run_at": None,
            "next_run_at": None,
            "run_count": 0,
        }
        self._path(job_id).write_text(json.dumps(entry, indent=2))
        return entry

    def get(self, job_id: str) -> dict | None:
        """Load a schedule by ID."""
        p = self._path(job_id)
        if not p.exists():
            return None
        return json.loads(p.read_text())

    def list_all(self) -> list[dict]:
        """List all schedules."""
        results = []
        for p in self.base_dir.glob("*.json"):
            try:
                results.append(json.loads(p.read_text()))
            except Exception:
                pass
        return sorted(results, key=lambda x: x.get("created_at", ""))

    def update(self, job_id: str, **fields) -> dict | None:
        """Update specific fields of a schedule."""
        entry = self.get(job_id)
        if not entry:
            return None
        entry.update(fields)
        self._path(job_id).write_text(json.dumps(entry, indent=2))
        return entry

    def delete(self, job_id: str) -> bool:
        """Delete a schedule."""
        p = self._path(job_id)
        if p.exists():
            p.unlink()
            return True
        return False


# ---------------------------------------------------------------------------
# Thread history (lightweight — agent results, not messages)
# ---------------------------------------------------------------------------


class ThreadStorage:
    """Stores agent run results per thread for history / retrieval.

    Thread history is stored at  {thread_dir}/{thread_id}/history.jsonl
    One JSON dict per line (ndjson), ordered newest first.
    """

    def __init__(self, base_dir: Path | None = None):
        cfg = get_app_config()
        self.base_dir = base_dir or cfg.thread_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def append(self, thread_id: str, entry: dict) -> None:
        """Append a run result entry to the thread's history."""
        t_dir = self.base_dir / thread_id
        t_dir.mkdir(parents=True, exist_ok=True)
        hist_file = t_dir / "history.jsonl"
        dt = datetime.utcnow()
        entry["_ts"] = dt.isoformat()
        hist_file.open("a").write(json.dumps(entry) + "\n")

    def get_history(self, thread_id: str, limit: int = 10) -> list[dict]:
        """Get the last `limit` run results for a thread."""
        import io

        t_dir = self.base_dir / thread_id
        hist_file = t_dir / "history.jsonl"
        if not hist_file.exists():
            return []

        lines = hist_file.read_text().strip().split("\n")
        entries = []
        for line in reversed(lines[-limit:]):
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
        return entries

    def list_threads(self, limit: int = 20) -> list[dict]:
        """List recent threads."""
        threads = []
        for t_dir in sorted(
            self.base_dir.iterdir(),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]:
            if not t_dir.is_dir():
                continue
            hist_file = t_dir / "history.jsonl"
            count = 0
            preview = ""
            if hist_file.exists():
                lines = hist_file.read_text().strip().split("\n")
                count = len(lines)
                if lines:
                    try:
                        last = json.loads(lines[-1])
                        preview = last.get("message", "")[:200]
                    except Exception:
                        pass
            threads.append({
                "thread_id": t_dir.name,
                "created_at": datetime.fromtimestamp(
                    t_dir.stat().st_ctime
                ).isoformat(),
                "updated_at": datetime.fromtimestamp(
                    t_dir.stat().st_mtime
                ).isoformat(),
                "message_count": count,
                "preview": preview,
            })
        return threads
