"""PlanMiddleware — loads plan context into prompt.

before_llm: reads plans from PlanStore, computes progress,
            formats plan_context into signals for prompt injection.

No before_tools hook needed: plan tools are host-only tools
that write to PlanStore directly.
"""

from nanodeer.agent.state import ThreadState, TurnSignals
from nanodeer.plan.storage import PlanStore
from nanodeer.plan.types import StepStatus

from .base import Middleware


def _compute_plan_context(plan_store: PlanStore) -> str:
    """Build plan context string from all plans and their steps."""
    plans = plan_store.list()
    if not plans:
        return ""

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

    return "\n".join(parts)


class PlanMiddleware(Middleware):
    """Loads plan context into signals.plan_context."""

    def __init__(self, plan_store: PlanStore | None = None):
        self._plan_store = plan_store or PlanStore()

    async def before_llm_streaming(self, state: ThreadState, signals: TurnSignals):
        context = _compute_plan_context(self._plan_store)
        if context:
            signals.plan_context = context
            signals.events.append({"type": "plan_context"})
        return
        yield
