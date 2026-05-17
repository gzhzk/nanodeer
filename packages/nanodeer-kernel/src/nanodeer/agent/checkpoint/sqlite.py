"""SqliteCheckpointer — ThreadState persistence via SQLite.

Replaces FileCheckpointer: stores messages as rows with role-based type
discrimination, avoiding Pydantic serialization bugs with dataclass subclasses.

Schema:
    threads    — thread_id, title, system_prompt, artifacts (JSON), timestamps
    messages   — id, thread_id, role, content, msg_id, tool_call_id, tool_name, tool_calls (JSON)
                 role column drives reconstruction of HumanMessage/AIMessage/ToolMessage
"""

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    MessageRole,
    SystemMessage,
    ToolCall,
    ToolMessage,
)
from ..state import ThreadState
from .base import Checkpointer


def _message_to_row(thread_id: str, msg: BaseMessage) -> dict[str, Any]:
    d = msg.to_dict()
    return {
        "thread_id": thread_id,
        "role": d["role"],
        "content": d["content"],
        "msg_id": d.get("id"),
        "tool_call_id": d.get("tool_call_id"),   # ToolMessage only
        "tool_name": d.get("name"),               # ToolMessage only (tool name, not the field name)
        "tool_calls": json.dumps(d["tool_calls"]) if d.get("tool_calls") else None,  # AIMessage only
    }


def _row_to_message(row: dict[str, Any]) -> BaseMessage:
    role = row["role"]
    if role == MessageRole.HUMAN.value:
        return HumanMessage(content=row["content"], id=row["msg_id"])
    if role == MessageRole.AI.value:
        tcs_raw = row.get("tool_calls")
        tool_calls = None
        if tcs_raw:
            tcs_data = json.loads(tcs_raw) if isinstance(tcs_raw, str) else tcs_raw
            tool_calls = [ToolCall(**tc) for tc in tcs_data]
        return AIMessage(content=row["content"], id=row["msg_id"], tool_calls=tool_calls)
    if role == MessageRole.TOOL.value:
        return ToolMessage(
            content=row["content"],
            id=row["msg_id"],
            tool_call_id=row.get("tool_call_id"),
            name=row.get("tool_name"),
        )
    if role == MessageRole.SYSTEM.value:
        return SystemMessage(content=row["content"], id=row["msg_id"])
    raise ValueError(f"Unknown message role: {role}")


class SqliteCheckpointer(Checkpointer):
    """ThreadState persistence via SQLite.

    Single DB file at ``{db_path}/threads.db``.
    Uses WAL mode for read-concurrent safety.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            db_file = self.db_path / "threads.db"
            self._conn = sqlite3.connect(str(db_file))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS threads (
                thread_id     TEXT PRIMARY KEY,
                title         TEXT,
                system_prompt TEXT,
                artifacts     TEXT,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id     TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
                role          TEXT NOT NULL,
                content       TEXT NOT NULL,
                msg_id        TEXT,
                tool_call_id  TEXT,
                tool_name     TEXT,
                tool_calls    TEXT,
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        conn.commit()

    # ------------------------------------------------------------------
    # Synchronous implementations (run via run_in_executor)
    # ------------------------------------------------------------------

    def _sync_save(self, thread_id: str, state: ThreadState) -> None:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()

        # Preserve original created_at on re-save
        row = conn.execute(
            "SELECT created_at FROM threads WHERE thread_id = ?", (thread_id,)
        ).fetchone()
        created_at = row["created_at"] if row else now

        conn.execute(
            """INSERT OR REPLACE INTO threads
               (thread_id, title, system_prompt, artifacts, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                thread_id,
                state.title,
                state.system_prompt,
                json.dumps(state.artifacts) if state.artifacts else None,
                created_at,
                now,
            ),
        )

        # Replace all messages atomically
        conn.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
        for msg in state.messages:
            r = _message_to_row(thread_id, msg)
            conn.execute(
                """INSERT INTO messages
                   (thread_id, role, content, msg_id, tool_call_id, tool_name, tool_calls)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (r["thread_id"], r["role"], r["content"], r["msg_id"],
                 r["tool_call_id"], r["tool_name"], r["tool_calls"]),
            )
        conn.commit()

    def _sync_load(self, thread_id: str) -> ThreadState | None:
        conn = self._get_conn()
        cur = conn.execute("SELECT * FROM threads WHERE thread_id = ?", (thread_id,))
        thread_row = cur.fetchone()
        if thread_row is None:
            return None

        cur = conn.execute(
            "SELECT * FROM messages WHERE thread_id = ? ORDER BY id", (thread_id,),
        )
        messages = [_row_to_message(dict(r)) for r in cur.fetchall()]

        artifacts_raw = thread_row["artifacts"]
        artifacts = json.loads(artifacts_raw) if artifacts_raw else []

        return ThreadState(
            thread_id=thread_row["thread_id"],
            title=thread_row["title"],
            system_prompt=thread_row["system_prompt"],
            artifacts=artifacts,
            messages=messages,
        )

    def _sync_list_threads(self) -> list[str]:
        conn = self._get_conn()
        cur = conn.execute("SELECT thread_id FROM threads ORDER BY updated_at DESC")
        return [row["thread_id"] for row in cur.fetchall()]

    def _sync_delete(self, thread_id: str) -> bool:
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
        conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Async public API
    # ------------------------------------------------------------------

    async def save(self, thread_id: str, state: ThreadState) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._sync_save, thread_id, state)

    async def load(self, thread_id: str) -> ThreadState | None:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_load, thread_id)

    async def list_threads(self) -> list[str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_list_threads)

    async def delete(self, thread_id: str) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_delete, thread_id)
