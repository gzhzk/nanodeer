"""List plans tool — view plans and their steps."""

from langchain_core.tools import tool

from ..plan.storage import PlanStore
from ..plan.types import StepStatus


def _status_icon(status: StepStatus) -> str:
    return {
        StepStatus.PENDING: "[ ]",
        StepStatus.IN_PROGRESS: "[*]",
        StepStatus.COMPLETED: "[x]",
        StepStatus.BLOCKED: "[!]",
        StepStatus.FAILED: "[-]",
    }.get(status, "[ ]")


@tool
def list_plans(plan_id: str | None = None) -> str:
    """List plans and their steps.

    Use plan_id to view a specific plan with all step details.
    Omit plan_id to see a summary of all plans.

    Args:
        plan_id: Optional plan ID to view in detail.

    Returns:
        Formatted list of plans and steps.
        "(no plans)" if empty.
    """
    store = PlanStore()

    if plan_id:
        plan = store.load(plan_id)
        if plan is None:
            return f"Plan `{plan_id}` not found."
        return _format_plan_detail(plan)

    plans = store.list()
    if not plans:
        return "(no plans)"

    lines = []
    for plan in plans:
        pct = plan.progress_pct
        status_tag = plan.status.value
        icon = "[x]" if pct == 100 and plan.status.value != "failed" else "[*]" if pct > 0 else "[ ]"
        title_part = f" - {plan.title}" if plan.title else ""
        lines.append(f"{icon} {plan.plan_id}{title_part}")
        lines.append(f"   Goal: {plan.goal}")
        lines.append(f"   Status: {status_tag}  Steps: {plan.completed_count}/{plan.total_count} ({pct}%)")
        lines.append("")

    return "\n".join(lines)


def _format_plan_detail(plan) -> str:
    lines = [
        f"Plan: {plan.plan_id}",
        f"Goal: {plan.goal}",
        f"Status: {plan.status.value}",
    ]
    if plan.title:
        lines.append(f"Title: {plan.title}")
    pct = plan.progress_pct
    if plan.steps:
        lines.append(f"Progress: {plan.completed_count}/{plan.total_count} ({pct}%)")
        lines.append("")
        for step in plan.steps:
            line = f"  {_status_icon(step.status)} {step.content}  (id={step.id})"
            if step.dependencies:
                line += f"  depends: {', '.join(step.dependencies)}"
            if step.assigned_to:
                line += f"  → {step.assigned_to}"
            lines.append(line)
            if step.result:
                lines.append(f"    result: {step.result[:200]}")
    else:
        lines.append("\n(no steps yet)")

    return "\n".join(lines)
