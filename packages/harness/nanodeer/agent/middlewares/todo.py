"""TodoMiddleware — parses todo tool results and updates state.todos.

before_llm: reads state.messages for write_todo / complete_todo results,
            applies merge_todos reducer to state.todos.
"""

import re

from langchain_core.messages import ToolMessage

from nanodeer.agent.state import ThreadState

from .base import Middleware

# Regex to extract todo id from tool results: "... (id=xxx)"
_ID_EXTRACT = re.compile(r"\(id=([a-zA-Z0-9-]+)\)")


class TodoMiddleware(Middleware):
    """Parses todo tool results, merges into state.todos via reducer."""

    async def before_llm(self, state: ThreadState) -> None:
        updates: list[dict] = []

        for msg in state.messages:
            if not isinstance(msg, ToolMessage):
                continue

            tool_name = getattr(msg, "name", None)
            content = msg.content or ""

            if tool_name == "write_todo":
                updates.append(self._parse_write_result(content))
            elif tool_name == "complete_todo":
                updates.append(self._parse_complete_result(content))

        # Merge into state.todos — reducer handles id-based merge
        if updates:
            state.todos = updates

    def _parse_write_result(self, content: str) -> dict:
        """Parse write_todo result: "Todo added: [ ] task (id=xxx)"""
        todo_id = self._extract_id(content)
        if not todo_id:
            return {}

        # Determine status from checkbox: [ ] pending, [>] in_progress, [x] completed
        status = "pending"
        if "[x]" in content:
            status = "completed"
        elif "[>]" in content:
            status = "in_progress"

        # Extract content: "[ ] task content (id=xxx)" → "task content"
        match = re.search(r"\[[x >]\]\s+(.+?)(?:\s+\(id=|$)", content)
        todo_content = match.group(1).strip() if match else ""

        return {"id": todo_id, "content": todo_content, "status": status}

    def _parse_complete_result(self, content: str) -> dict:
        """Parse complete_todo result: "Todo xxx completed" → mark complete"""
        todo_id = self._extract_id(content)
        if not todo_id:
            return {}
        return {"id": todo_id, "status": "completed"}

    def _extract_id(self, content: str) -> str | None:
        match = _ID_EXTRACT.search(content)
        return match.group(1) if match else None
