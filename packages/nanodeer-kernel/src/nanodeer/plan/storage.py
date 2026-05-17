"""PlanStore — file-based Plan persistence with embedded steps.

Storage layout:
  ~/.nanodeer/plans/{plan_id}.json   — full Plan document (metadata + steps)
  ~/.nanodeer/plans/index.json        — lightweight index for list_plans
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from .types import Plan

PLANS_ROOT = Path.home() / ".nanodeer" / "plans"


class PlanStore:
    """File-based plan store. Each plan is a single JSON file with embedded steps."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or PLANS_ROOT
        self.root.mkdir(parents=True, exist_ok=True)

    def _plan_path(self, plan_id: str) -> Path:
        return self.root / f"{plan_id}.json"

    def _index_path(self) -> Path:
        return self.root / "index.json"

    def _load_index(self) -> list[dict]:
        path = self._index_path()
        if not path.exists():
            return []
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def _save_index(self, entries: list[dict]) -> None:
        fd, tmp = tempfile.mkstemp(suffix=".json", dir=str(self.root))
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self._index_path())
        except Exception:
            os.unlink(tmp)

    def save(self, plan: Plan) -> None:
        """Save full plan document (metadata + steps) to disk."""
        path = self._plan_path(plan.plan_id)
        with open(path, "w") as f:
            json.dump(plan.to_dict(), f, indent=2, ensure_ascii=False)

        # Update index
        summary = {
            "plan_id": plan.plan_id,
            "goal": plan.goal,
            "title": plan.title,
            "status": plan.status.value,
            "total": plan.total_count,
            "completed": plan.completed_count,
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
        }
        index = self._load_index()
        for i, entry in enumerate(index):
            if entry.get("plan_id") == plan.plan_id:
                index[i] = summary
                break
        else:
            index.append(summary)
        self._save_index(index)

    def load(self, plan_id: str) -> Optional[Plan]:
        """Load full plan by ID."""
        path = self._plan_path(plan_id)
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return Plan.from_dict(json.load(f))
        except (json.JSONDecodeError, OSError):
            return None

    def delete(self, plan_id: str) -> bool:
        """Delete plan. Returns True if deleted."""
        path = self._plan_path(plan_id)
        if not path.exists():
            return False
        path.unlink()
        index = self._load_index()
        index = [e for e in index if e.get("plan_id") != plan_id]
        self._save_index(index)
        return True

    def list(self) -> list[Plan]:
        """List all plans (loads full documents)."""
        return [self.load(e["plan_id"]) for e in self._load_index() if self.load(e["plan_id"]) is not None]
