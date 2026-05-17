"""Tests for PlanMiddleware — loads plan context into prompt."""

import tempfile
from pathlib import Path

import pytest

from nanodeer.agent.middlewares.plan import PlanMiddleware, _compute_plan_context
from nanodeer.agent.state import ThreadState, TurnSignals
from nanodeer.plan.storage import PlanStore
from nanodeer.plan.types import Plan, Step, StepStatus


@pytest.fixture
def tmp():
    return Path(tempfile.mkdtemp())


@pytest.fixture
def state():
    return ThreadState()


@pytest.fixture
def signals():
    return TurnSignals()


class TestComputePlanContext:
    def test_empty_no_plans(self, tmp):
        assert _compute_plan_context(PlanStore(root=tmp)) == ""

    def test_with_plan_and_steps(self, tmp):
        store = PlanStore(root=tmp)
        plan = Plan(plan_id="plan-1", goal="Test plan", steps=[
            Step(content="step 1", status=StepStatus.COMPLETED),
            Step(content="step 2"),
        ])
        store.save(plan)

        context = _compute_plan_context(store)
        assert "Test plan" in context
        assert "[x] step 1" in context
        assert "[ ] step 2" in context
        assert "1/2 steps" in context

    def test_with_dependencies(self, tmp):
        store = PlanStore(root=tmp)
        plan = Plan(plan_id="plan-2", goal="Deps test", steps=[
            Step(content="first", id="a"),
            Step(content="second", id="b", dependencies=["a"]),
        ])
        store.save(plan)

        context = _compute_plan_context(store)
        assert "depends:" in context
        assert "a" in context

    def test_with_assigned_step(self, tmp):
        store = PlanStore(root=tmp)
        plan = Plan(plan_id="plan-3", goal="Assign test", steps=[
            Step(content="do this", assigned_to="sub-a1b2"),
        ])
        store.save(plan)

        context = _compute_plan_context(store)
        assert "assigned:" in context
        assert "sub-a1b2" in context


class TestPlanMiddleware:
    async def test_sets_plan_context_on_signals(self, tmp, state, signals):
        """Has plans → sets plan_context."""
        store = PlanStore(root=tmp)
        mw = PlanMiddleware(plan_store=store)

        plan = Plan(plan_id="plan-1", goal="Test", steps=[Step(content="some task")])
        store.save(plan)

        async for _ in mw.before_llm_streaming(state, signals):
            pass

        assert signals.plan_context is not None
        assert "some task" in signals.plan_context

    async def test_omits_plan_context_when_empty(self, tmp, state, signals):
        """No plans → plan_context stays None."""
        store = PlanStore(root=tmp)
        mw = PlanMiddleware(plan_store=store)

        async for _ in mw.before_llm_streaming(state, signals):
            pass

        assert signals.plan_context is None
