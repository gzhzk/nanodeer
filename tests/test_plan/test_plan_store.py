"""Tests for PlanStore — file-based plan persistence with embedded steps."""

import json
import tempfile
from pathlib import Path

from nanodeer.plan.storage import PlanStore
from nanodeer.plan.types import Plan, Step, StepStatus, PlanStatus


class TestPlanStore:
    def setup_method(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = PlanStore(root=self.tmp)

    def test_save_and_load(self):
        plan = Plan(plan_id="plan-1", goal="Test goal", title="My Plan",
                    steps=[Step(content="step 1")])
        self.store.save(plan)

        loaded = self.store.load("plan-1")
        assert loaded is not None
        assert loaded.plan_id == "plan-1"
        assert loaded.goal == "Test goal"
        assert loaded.title == "My Plan"
        assert len(loaded.steps) == 1
        assert loaded.steps[0].content == "step 1"

    def test_load_missing_returns_none(self):
        assert self.store.load("nonexistent") is None

    def test_delete(self):
        plan = Plan(plan_id="plan-2", goal="Delete me")
        self.store.save(plan)
        assert self.store.load("plan-2") is not None

        result = self.store.delete("plan-2")
        assert result is True
        assert self.store.load("plan-2") is None

    def test_delete_nonexistent(self):
        assert self.store.delete("ghost") is False

    def test_list(self):
        self.store.save(Plan(plan_id="a", goal="Goal A", steps=[Step(content="s1")]))
        self.store.save(Plan(plan_id="b", goal="Goal B", steps=[Step(content="s2")]))

        plans = self.store.list()
        assert len(plans) == 2
        assert {p.plan_id for p in plans} == {"a", "b"}

    def test_update_existing(self):
        plan = Plan(plan_id="plan-3", goal="Original")
        self.store.save(plan)

        plan.goal = "Updated"
        plan.steps = [Step(content="new step")]
        self.store.save(plan)

        loaded = self.store.load("plan-3")
        assert loaded.goal == "Updated"
        assert len(loaded.steps) == 1
        assert loaded.steps[0].content == "new step"

    def test_index_updated_on_save(self):
        self.store.save(Plan(plan_id="x", goal="X"))
        index_path = self.tmp / "index.json"
        assert index_path.exists()
        with open(index_path) as f:
            index = json.load(f)
        assert len(index) == 1
        assert index[0]["plan_id"] == "x"

    def test_progress_properties(self):
        plan = Plan(plan_id="p1", goal="progress", steps=[
            Step(content="done", status=StepStatus.COMPLETED),
            Step(content="doing", status=StepStatus.IN_PROGRESS),
            Step(content="todo"),
        ])
        assert plan.completed_count == 1
        assert plan.total_count == 3
        assert plan.progress_pct == 33

    def test_serialization_roundtrip(self):
        plan = Plan(plan_id="rt", goal="Roundtrip", title="RT",
                    status=PlanStatus.ACTIVE, steps=[
                        Step(content="s1", dependencies=["step-a"], assigned_to="sub-1", result="done"),
                        Step(content="s2", status=StepStatus.BLOCKED, notes="waiting"),
                    ])
        data = plan.to_dict()
        restored = Plan.from_dict(data)
        assert restored.plan_id == "rt"
        assert restored.status == PlanStatus.ACTIVE
        assert len(restored.steps) == 2
        assert restored.steps[0].dependencies == ["step-a"]
        assert restored.steps[0].assigned_to == "sub-1"
        assert restored.steps[0].result == "done"
        assert restored.steps[1].status == StepStatus.BLOCKED
        assert restored.steps[1].notes == "waiting"
