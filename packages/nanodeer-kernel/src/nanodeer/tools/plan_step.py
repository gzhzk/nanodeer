"""Plan step tools — add and update steps within a plan."""

import uuid

from langchain_core.tools import tool

from ..plan.storage import PlanStore
from ..plan.types import PlanStatus, Step, StepStatus


@tool
def add_step(
    plan_id: str,
    content: str,
    dependencies: list[str] | None = None,
    assigned_to: str | None = None,
) -> str:
    """Add a step to an existing plan.

    Args:
        plan_id: The plan ID to add the step to.
        content: The step description.
        dependencies: Optional list of step IDs this step depends on.
        assigned_to: Optional subagent ID or "main" to assign this step.

    Returns:
        Confirmation message with the step ID.
    """
    store = PlanStore()
    plan = store.load(plan_id)
    if plan is None:
        return f"Plan `{plan_id}` not found."

    step = Step(
        content=content,
        dependencies=dependencies or [],
        assigned_to=assigned_to,
    )
    plan.steps.append(step)
    if plan.status == PlanStatus.DRAFTING:
        plan.status = PlanStatus.ACTIVE
    plan.updated_at = __import__("datetime").datetime.now().isoformat()
    store.save(plan)
    return f"Step added: {step.to_markdown()}\nID: {step.id}\nPlan: {plan_id}"


@tool
def update_step(
    plan_id: str,
    step_id: str,
    status: str | None = None,
    result: str | None = None,
    notes: str | None = None,
) -> str:
    """Update a step's status, result, or notes.

    Args:
        plan_id: The plan ID containing the step.
        step_id: The step ID to update.
        status: New status: "pending", "in_progress", "completed", "blocked", "failed".
        result: Optional result or output of the step.
        notes: Optional notes about the step.

    Returns:
        Confirmation message.
    """
    store = PlanStore()
    plan = store.load(plan_id)
    if plan is None:
        return f"Plan `{plan_id}` not found."

    step = next((s for s in plan.steps if s.id == step_id), None)
    if step is None:
        return f"Step `{step_id}` not found in plan `{plan_id}`."

    if status is not None:
        step.status = StepStatus(status)
    if result is not None:
        step.result = result
    if notes is not None:
        step.notes = notes

    step.updated_at = __import__("datetime").datetime.now().isoformat()
    plan.updated_at = step.updated_at

    # Auto-update plan status
    if step.status == StepStatus.FAILED:
        plan.status = PlanStatus.FAILED
    elif plan.completed_count == plan.total_count and plan.total_count > 0:
        plan.status = PlanStatus.COMPLETED
    elif step.status in (StepStatus.IN_PROGRESS, StepStatus.PENDING) and plan.status in (PlanStatus.DRAFTING, PlanStatus.COMPLETED):
        plan.status = PlanStatus.ACTIVE

    store.save(plan)
    return f"Step updated: {step.to_markdown()}  (id={step.id})"
