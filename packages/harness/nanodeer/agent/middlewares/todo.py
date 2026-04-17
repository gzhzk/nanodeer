"""TodoMiddleware — parses write_todo tool results and updates state.todos.

before_llm: reads state.messages for write_todo results,
            applies merge_todos reducer to state.todos.

Note: write_todo tool supports status update via status parameter.
      No separate complete_todo tool exists.
"""

import re

from nanodeer.agent.messages import ToolMessage

from nanodeer.agent.state import ThreadState, TurnSignals

from .base import Middleware

_ID_EXTRACT = re.compile(r"\(id=([a-zA-Z0-9-]+)\)")


class TodoMiddleware(Middleware):
    """Parses write_todo results, merges into state.todos via reducer."""

    async def before_llm(self, state: ThreadState, signals: TurnSignals) -> None:
        updates: list[dict] = []

        for msg in state.messages:
            if not isinstance(msg, ToolMessage):
                continue
            if getattr(msg, "name", None) != "write_todo":
                continue

            todo = self._parse_result(msg.content or "")
            if todo:
                updates.append(todo)

        if updates:
            state.todos = updates

    def _parse_result(self, content: str) -> dict:
        """Parse write_todo result: "Todo added: [ ] task (id=xxx)" or
        "Todo updated: [x] task (id=xxx)"."""
        todo_id = self._extract_id(content)
        if not todo_id:
            return {}

        status = "pending"
        if "[x]" in content:
            status = "completed"
        elif "[>]" in content:
            status = "in_progress"

        match = re.search(r"\[[x >]\]\s+(.+?)(?:\s+\(id=|$)", content)
        todo_content = match.group(1).strip() if match else ""

        return {"id": todo_id, "content": todo_content, "status": status}

    def _extract_id(self, content: str) -> str | None:
        match = _ID_EXTRACT.search(content)
        return match.group(1) if match else None
