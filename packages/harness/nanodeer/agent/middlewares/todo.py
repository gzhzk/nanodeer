"""TodoMiddleware — loads todos from store into state.

before_llm: loads state.todos directly from TodoStore using thread_id.
"""

from nanodeer.agent.state import ThreadState, TurnSignals
from nanodeer.plan.loader import TodoStore

from .base import Middleware


class TodoMiddleware(Middleware):
    """Loads todos from store into state.todos before each LLM call.

    Direct store read — no text parsing, no message inspection.
    write_todo is synchronous and has already persisted to store before
    this middleware runs.
    """

    async def before_llm(self, state: ThreadState, signals: TurnSignals) -> None:
        store = TodoStore()
        state.todos = store.load("default")
