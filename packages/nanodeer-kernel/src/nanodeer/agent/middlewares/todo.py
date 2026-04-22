"""TodoMiddleware — loads todos from store into state.

before_llm: loads state.todos directly from TodoStore using thread_id.
"""

from nanodeer.agent.state import ThreadState, TurnSignals
from nanodeer.plan.loader import TodoStore

from .base import Middleware


class TodoMiddleware(Middleware):
    """Loads todos from store into state.todos before each LLM call."""

    def __init__(self):
        self._store = TodoStore()

    async def before_llm_streaming(self, state: ThreadState, signals: TurnSignals):
        state.todos = self._store.load("default")
        signals.events.append({
            "type": "todos",
            "count": len(state.todos),
        })
        return
        yield
