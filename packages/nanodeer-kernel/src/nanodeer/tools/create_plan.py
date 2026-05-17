"""Plan tool — create a plan with optional initial steps."""

import uuid

from langchain_core.tools import tool

from ..plan.storage import PlanStore
from ..plan.types import Plan, Step


@tool
def create_plan(
    goal: str,
    title: str = "",
    steps: list[str] | None = None,
) -> str:
    """Create a new plan to track a multi-step task.

    After creating a plan, use add_step to add more steps,
    update_step to mark progress, and list_plans to view status.

    Args:
        goal: The overall goal or objective of this plan.
        title: Optional short title for the plan.
        steps: Optional list of step descriptions to create initial steps.

    Returns:
        Confirmation message with the plan ID.
    """
    pid = f"plan-{uuid.uuid4().hex[:8]}"
    plan = Plan(plan_id=pid, goal=goal, title=title)

    if steps:
        plan.steps = [Step(content=s) for s in steps]

    PlanStore().save(plan)
    msg = f"Plan created: {pid}\nGoal: {goal}"
    if title:
        msg += f"\nTitle: {title}"
    if steps:
        msg += f"\nSteps: {len(steps)}"
    return msg
