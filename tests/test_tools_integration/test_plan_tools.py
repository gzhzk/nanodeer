"""Tests for plan tools: create_plan, add_step, update_step, list_plans."""
import pytest
from unittest.mock import MagicMock, patch

from nanodeer.tools.create_plan import create_plan
from nanodeer.tools.plan_step import add_step, update_step
from nanodeer.tools.list_plans import list_plans
from nanodeer.plan.types import Plan, Step, StepStatus


class TestCreatePlanTool:
    def test_invoke_minimal(self):
        """Creating a plan with just a goal works."""
        with patch("nanodeer.tools.create_plan.PlanStore") as MockStore:
            mock_store = MagicMock()
            MockStore.return_value = mock_store

            result = create_plan.invoke({"goal": "Build a website"})

            assert "Plan created:" in result
            assert "Build a website" in result
            mock_store.save.assert_called_once()
            saved = mock_store.save.call_args[0][0]
            assert saved.goal == "Build a website"
            assert saved.title == ""

    def test_invoke_with_steps(self):
        """Creating a plan with initial steps works."""
        with patch("nanodeer.tools.create_plan.PlanStore") as MockStore:
            mock_store = MagicMock()
            MockStore.return_value = mock_store

            result = create_plan.invoke({
                "goal": "Build a website",
                "steps": ["Design", "Implement", "Test"],
            })

            assert "Steps: 3" in result
            saved = mock_store.save.call_args[0][0]
            assert len(saved.steps) == 3

    def test_invoke_with_title(self):
        """Creating a plan with title works."""
        with patch("nanodeer.tools.create_plan.PlanStore") as MockStore:
            mock_store = MagicMock()
            MockStore.return_value = mock_store

            result = create_plan.invoke({
                "goal": "Build a website",
                "title": "Website Project",
            })

            assert "Title: Website Project" in result


class TestAddStepTool:
    def test_invoke_success(self):
        """Adding a step to an existing plan works."""
        with patch("nanodeer.tools.plan_step.PlanStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load.return_value = Plan(plan_id="plan-abc", goal="Test")
            MockStore.return_value = mock_store

            result = add_step.invoke({
                "plan_id": "plan-abc",
                "content": "Do something",
            })

            assert "Step added:" in result
            assert "plan-abc" in result
            assert "Do something" in result
            mock_store.save.assert_called_once()

    def test_invoke_plan_not_found(self):
        """Adding step to nonexistent plan returns error."""
        with patch("nanodeer.tools.plan_step.PlanStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load.return_value = None
            MockStore.return_value = mock_store

            result = add_step.invoke({
                "plan_id": "plan-xyz",
                "content": "Do something",
            })

            assert "not found" in result

    def test_invoke_with_assigned(self):
        """Adding a step with assigned_to works."""
        with patch("nanodeer.tools.plan_step.PlanStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load.return_value = Plan(plan_id="plan-abc", goal="Test")
            MockStore.return_value = mock_store

            result = add_step.invoke({
                "plan_id": "plan-abc",
                "content": "Research topic",
                "assigned_to": "sub-wkr1",
            })

            assert "sub-wkr1" in result or "Step added" in result
            saved = mock_store.save.call_args[0][0]
            assert saved.steps[-1].assigned_to == "sub-wkr1"


class TestUpdateStepTool:
    def test_invoke_update_status(self):
        """Updating step status works."""
        with patch("nanodeer.tools.plan_step.PlanStore") as MockStore:
            mock_store = MagicMock()
            plan = Plan(plan_id="plan-abc", goal="Test", steps=[Step(id="step-1", content="Do it")])
            mock_store.load.return_value = plan
            MockStore.return_value = mock_store

            result = update_step.invoke({
                "plan_id": "plan-abc",
                "step_id": "step-1",
                "status": "completed",
            })

            assert "Step updated:" in result
            assert "step-1" in result
            saved = mock_store.save.call_args[0][0]
            assert saved.steps[0].status == StepStatus.COMPLETED

    def test_invoke_plan_not_found(self):
        """Updating step in nonexistent plan returns error."""
        with patch("nanodeer.tools.plan_step.PlanStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load.return_value = None
            MockStore.return_value = mock_store

            result = update_step.invoke({
                "plan_id": "plan-xyz",
                "step_id": "step-1",
                "status": "completed",
            })

            assert "not found" in result

    def test_invoke_step_not_found(self):
        """Updating nonexistent step returns error."""
        with patch("nanodeer.tools.plan_step.PlanStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load.return_value = Plan(plan_id="plan-abc", goal="Test")
            MockStore.return_value = mock_store

            result = update_step.invoke({
                "plan_id": "plan-abc",
                "step_id": "step-nonexistent",
                "status": "completed",
            })

            assert "not found" in result

    def test_invoke_with_result(self):
        """Updating step with result works."""
        with patch("nanodeer.tools.plan_step.PlanStore") as MockStore:
            mock_store = MagicMock()
            plan = Plan(plan_id="plan-abc", goal="Test", steps=[Step(id="step-1", content="Do it")])
            mock_store.load.return_value = plan
            MockStore.return_value = mock_store

            result = update_step.invoke({
                "plan_id": "plan-abc",
                "step_id": "step-1",
                "status": "completed",
                "result": "All done!",
            })

            assert "Step updated:" in result
            saved = mock_store.save.call_args[0][0]
            assert saved.steps[0].result == "All done!"
            assert saved.steps[0].status == StepStatus.COMPLETED


class TestListPlansTool:
    def test_invoke_empty(self):
        """No plans returns '(no plans)'."""
        with patch("nanodeer.tools.list_plans.PlanStore") as MockStore:
            mock_store = MagicMock()
            mock_store.list.return_value = []
            MockStore.return_value = mock_store

            result = list_plans.invoke({})
            assert result == "(no plans)"

    def test_invoke_with_plans(self):
        """Returns formatted list of plans."""
        with patch("nanodeer.tools.list_plans.PlanStore") as MockStore:
            mock_store = MagicMock()
            plan = Plan(plan_id="plan-a", goal="Goal A",
                        steps=[Step(content="s1", status=StepStatus.COMPLETED)])
            mock_store.list.return_value = [plan]
            MockStore.return_value = mock_store

            result = list_plans.invoke({})

            assert "plan-a" in result
            assert "Goal A" in result
            assert "1/1" in result

    def test_invoke_plan_detail(self):
        """Viewing a specific plan shows step details."""
        with patch("nanodeer.tools.list_plans.PlanStore") as MockStore:
            mock_store = MagicMock()
            plan = Plan(plan_id="plan-a", goal="Goal A",
                        steps=[Step(id="step-1", content="Step one", status=StepStatus.COMPLETED)])
            mock_store.load.return_value = plan
            MockStore.return_value = mock_store

            result = list_plans.invoke({"plan_id": "plan-a"})

            assert "Step one" in result
            assert "step-1" in result

    def test_invoke_plan_not_found(self):
        """Viewing a nonexistent plan returns error."""
        with patch("nanodeer.tools.list_plans.PlanStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load.return_value = None
            MockStore.return_value = mock_store

            result = list_plans.invoke({"plan_id": "plan-xyz"})
            assert "not found" in result
