"""SqliteCheckpointer — persists conversation messages + thread metadata.

Schema serves dual purpose:
  - Frontend: list_conversations() reads threads table for title/count/timestamps
  - Agent resume: load() reconstructs message history for LLM context

Not persisted (reconstructed at runtime):
  - sandbox state (resume creates fresh container + re-mounts volume)

Persisted run control:
  - next_action (FINISH or WAIT)
  - finish_reason
  - wait (question and required external input for WAIT)

See also: AgentState fields vs DB columns mapping in class doc.
"""

import asyncio
import json
import sqlite3
import threading
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
from ..state import AgentState, NextAction, WaitState
from .base import Checkpointer


_THREAD_COLS = ("thread_id", "title", "message_count", "created_at", "updated_at", "status")


def _message_to_row(thread_id: str, msg: BaseMessage) -> dict[str, Any]:
    d = msg.to_dict()
    return {
        "thread_id": thread_id,
        "role": d["role"],
        "content": d["content"],
        "msg_id": d.get("id"),
        "tool_call_id": d.get("tool_call_id"),
        "tool_name": d.get("name"),
        "tool_calls": json.dumps(d["tool_calls"]) if d.get("tool_calls") else None,
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
    """AgentState persistence via SQLite.

    Threads table stores frontend-facing metadata (title, message_count, timestamps).
    Messages table stores the full message history for LLM context reconstruction.

    Fields NOT persisted (reconstructed at runtime):
      - sandbox         ← resume creates fresh container

    ``next_action`` and ``wait`` are persisted so WAIT survives restarts.

    Single DB file at ``{db_path}/threads.db``.
    Uses WAL mode for read-concurrent safety.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.mkdir(parents=True, exist_ok=True)
        self._connections = threading.local()
        self._lock = asyncio.Lock()
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._connections, "conn", None)
        if conn is None:
            db_file = self.db_path / "threads.db"
            conn = sqlite3.connect(str(db_file))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._connections.conn = conn
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS threads (
                thread_id     TEXT PRIMARY KEY,
                title         TEXT,
                message_count INTEGER DEFAULT 0,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL,
                status        TEXT DEFAULT 'regular',
                run_outcome   TEXT,
                finish_reason TEXT,
                wait_state    TEXT,
                state_revision INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS messages (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id     TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
                role          TEXT NOT NULL,
                content       TEXT NOT NULL DEFAULT '',
                msg_id        TEXT,
                tool_call_id  TEXT,
                tool_name     TEXT,
                tool_calls    TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON messages(thread_id);
        """)
        conn.commit()
        # Additive migrations for existing databases. Inspecting the schema avoids
        # leaving failed ALTER statements on a connection later used by a worker.
        existing_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(threads)").fetchall()
        }
        for column, sql_type in (
            ("status", "TEXT DEFAULT 'regular'"),
            ("run_outcome", "TEXT"),
            ("finish_reason", "TEXT"),
            ("wait_state", "TEXT"),
            ("state_revision", "INTEGER DEFAULT 0"),
        ):
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE threads ADD COLUMN {column} {sql_type}")
        conn.commit()

    # ------------------------------------------------------------------
    # Synchronous implementations
    # ------------------------------------------------------------------

    def _sync_save(self, thread_id: str, state: AgentState) -> None:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()

        # Preserve original created_at on re-save
        row = conn.execute(
            "SELECT created_at, status FROM threads WHERE thread_id = ?", (thread_id,)
        ).fetchone()
        created_at = row["created_at"] if row else now

        # Archive is conversation metadata, not AgentState. A runtime checkpoint
        # must not silently unarchive the thread.
        status = row["status"] if row and row["status"] else "regular"
        run_outcome = state.next_action.value if state.next_action else None
        wait_state = state.wait.model_dump_json() if state.wait else None
        conn.execute(
            """INSERT OR REPLACE INTO threads
               (thread_id, title, message_count, created_at, updated_at, status,
                run_outcome, finish_reason, wait_state, state_revision)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                thread_id,
                state.title,
                len(state.messages),
                created_at,
                now,
                status,
                run_outcome,
                state.finish_reason,
                wait_state,
                state.revision,
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

    def _sync_load(self, thread_id: str) -> AgentState | None:
        conn = self._get_conn()
        cur = conn.execute("SELECT * FROM threads WHERE thread_id = ?", (thread_id,))
        thread_row = cur.fetchone()
        if thread_row is None:
            return None

        cur = conn.execute(
            "SELECT * FROM messages WHERE thread_id = ? ORDER BY id", (thread_id,),
        )
        messages = [_row_to_message(dict(r)) for r in cur.fetchall()]

        outcome_raw = thread_row["run_outcome"]
        try:
            next_action = NextAction(outcome_raw) if outcome_raw else None
        except ValueError:
            next_action = None

        wait_raw = thread_row["wait_state"]
        try:
            wait_state = WaitState.model_validate_json(wait_raw) if wait_raw else None
        except (ValueError, TypeError):
            wait_state = None

        return AgentState(
            thread_id=thread_row["thread_id"],
            title=thread_row["title"],
            messages=messages,
            next_action=next_action,
            wait=wait_state,
            finish_reason=thread_row["finish_reason"] or (
                "wait" if next_action == NextAction.WAIT else "completed"
            ),
            revision=thread_row["state_revision"] or 0,
        )

    def _sync_load_meta(self, thread_id: str) -> dict | None:
        """Lightweight metadata load — no messages, single query."""
        conn = self._get_conn()
        cur = conn.execute(
            "SELECT thread_id, title, message_count, created_at, updated_at, status, "
            "run_outcome, finish_reason, wait_state, state_revision "
            "FROM threads WHERE thread_id = ?",
            (thread_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        wait_state = json.loads(row["wait_state"]) if row["wait_state"] else None
        return {
            "thread_id": row["thread_id"],
            "title": row["title"],
            "message_count": row["message_count"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "status": row["status"] or "regular",
            "next_action": row["run_outcome"],
            "finish_reason": row["finish_reason"],
            "wait": wait_state,
            "revision": row["state_revision"] or 0,
        }

    def _sync_list_threads(self) -> list[dict]:
        """List all thread metadata (no messages)."""
        conn = self._get_conn()
        cur = conn.execute(
            "SELECT thread_id, title, message_count, created_at, updated_at, status, "
            "run_outcome, finish_reason, wait_state, state_revision "
            "FROM threads ORDER BY updated_at DESC"
        )
        rows = []
        for raw in cur.fetchall():
            row = dict(raw)
            row["next_action"] = row.pop("run_outcome")
            wait_raw = row.pop("wait_state")
            row["wait"] = json.loads(wait_raw) if wait_raw else None
            row["revision"] = row.pop("state_revision") or 0
            rows.append(row)
        return rows

    def _sync_delete(self, thread_id: str) -> bool:
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
        conn.commit()
        return cur.rowcount > 0

    def _sync_update_title(self, thread_id: str, title: str) -> bool:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "UPDATE threads SET title = ?, updated_at = ? WHERE thread_id = ?",
            (title, now, thread_id),
        )
        conn.commit()
        return cur.rowcount > 0

    def _sync_update_status(self, thread_id: str, status: str) -> bool:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "UPDATE threads SET status = ?, updated_at = ? WHERE thread_id = ?",
            (status, now, thread_id),
        )
        conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Async public API
    # ------------------------------------------------------------------

    async def save(self, thread_id: str, state: AgentState) -> None:
        async with self._lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._sync_save, thread_id, state)

    async def load(self, thread_id: str) -> AgentState | None:
        async with self._lock:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._sync_load, thread_id)

    async def load_meta(self, thread_id: str) -> dict | None:
        """Load thread metadata without fetching messages."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_load_meta, thread_id)

    async def list_threads(self) -> list[str]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._sync_list_threads)
        return [r["thread_id"] for r in result]

    async def list_conversations(self) -> list[dict]:
        """List all thread metadata (title, count, timestamps) — no messages loaded."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_list_threads)

    async def delete(self, thread_id: str) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_delete, thread_id)

    async def update_title(self, thread_id: str, title: str) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_update_title, thread_id, title)

    async def update_status(self, thread_id: str, status: str) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_update_status, thread_id, status)
