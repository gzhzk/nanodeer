"""NanoDeer HTTP API — FastAPI + SSE streaming.

Primary frontend-facing interface. Frontend (assistant-ui)
connects here directly via SSE.

Usage:
    python -m nanodeer.cli.api     # start server
    curl http://127.0.0.1:20266/health
"""

import asyncio
import json
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from nanodeer.config import get_config
from nanodeer.engine import NanoEngine

logger = logging.getLogger(__name__)

# Track running tasks per thread_id for cancellation
_running_tasks: dict[str, asyncio.Task] = {}

app = FastAPI(title="NanoDeer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_checkpointer():
    """Create SqliteCheckpointer from config."""
    from nanodeer.agent.checkpoint.sqlite import SqliteCheckpointer
    return SqliteCheckpointer(str(get_config().thread.db_path.expanduser().resolve()))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/info")
async def api_info():
    """Return runtime info including model details."""
    cfg = get_config()
    return {
        "provider": cfg.agents.defaults.provider,
        "model": cfg.agents.defaults.model,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(request: Request):
    """Streaming chat endpoint.

    Request (JSON)::
        {"prompt": "...", "thread_id": "..."}

    Response: SSE stream of events matching ``NanoEngine.run_streaming()``::

        event: message
        data: {"event":"llm_token","text":"Hello","threadId":"..."}
        event: message
        data: {"event":"tool_call","name":"bash","args":{...},"threadId":"..."}
        event: cancelled
        data: {"event":"cancelled","threadId":"..."}
    """
    body = await request.json()
    prompt = body.get("prompt", "").strip()
    thread_id = body.get("thread_id", "") or uuid.uuid4().hex

    if not prompt:
        return JSONResponse({"error": "prompt is required"}, status_code=400)

    engine = NanoEngine(get_config())

    async def event_generator():
        task = asyncio.current_task()
        _running_tasks[thread_id] = task
        try:
            async for event in engine.run_streaming(prompt=prompt, thread_id=thread_id):
                yield {"event": "message", "data": json.dumps(event)}
        except asyncio.CancelledError:
            yield {"event": "cancelled", "data": json.dumps({"event": "cancelled", "threadId": thread_id})}
        except Exception as exc:
            logger.exception("chat stream failed thread_id=%s", thread_id)
            yield {
                "event": "message",
                "data": json.dumps({
                    "event": "error",
                    "code": type(exc).__name__,
                    "message": str(exc) or type(exc).__name__,
                    "threadId": thread_id,
                }),
            }
        finally:
            _running_tasks.pop(thread_id, None)

    return EventSourceResponse(event_generator())


@app.post("/api/chat/cancel")
async def cancel_chat(request: Request):
    """Cancel a running chat by thread_id.

    Request (JSON)::
        {"thread_id": "..."}
    """
    body = await request.json()
    thread_id = body.get("thread_id")
    if not thread_id:
        return JSONResponse({"ok": False, "error": "thread_id is required"}, status_code=400)

    task = _running_tasks.get(thread_id)
    if task and not task.done():
        task.cancel()
        return {"ok": True, "thread_id": thread_id}
    return {"ok": False, "error": "no running task found", "thread_id": thread_id}


@app.get("/api/conversations")
async def list_conversations():
    """List all saved conversations (metadata only, no messages)."""
    cp = _make_checkpointer()
    conversations = await cp.list_conversations()
    return {"conversations": conversations}


@app.get("/api/workspace/summary")
async def workspace_summary():
    """Return lightweight workspace counts for the frontend sidebar."""
    from nanodeer.agent.memory.storage import MemoryStore
    from nanodeer.plan.storage import PlanStore

    memory = MemoryStore()
    plans = PlanStore().list()
    wiki_entries = memory.list_wiki_entries()
    projects = [
        entry for entry in wiki_entries
        if str(entry.get("path", "")).startswith("project/")
    ]
    user_memory = memory.load_user_memory()
    flat_memory = memory.load_memory()
    episodic_dates = memory.list_episodic()

    return {
        "projects": {
            "count": len(projects),
            "items": projects[:5],
        },
        "plans": {
            "count": len(plans),
            "active": sum(1 for plan in plans if plan.status.value == "active"),
            "items": [plan.to_dict() for plan in plans[:5]],
        },
        "memory": {
            "count": int(bool(user_memory)) + int(bool(flat_memory)) + len(episodic_dates),
            "has_user": bool(user_memory),
            "has_memory": bool(flat_memory),
            "episodic_days": len(episodic_dates),
        },
        "wiki": {
            "count": len(wiki_entries),
            "items": wiki_entries[:5],
        },
    }


@app.get("/api/conversations/{thread_id}")
async def get_conversation(thread_id: str):
    """Get a full conversation by thread_id."""
    cp = _make_checkpointer()
    state = await cp.load(thread_id)
    if not state:
        return JSONResponse({"error": "conversation not found"}, status_code=404)
    return {
        "thread_id": thread_id,
        "title": state.title or "",
        "status": state.status if hasattr(state, "status") else "regular",
        "messages": [msg.to_dict() for msg in state.messages],
    }


@app.get("/api/conversations/{thread_id}/meta")
async def get_conversation_meta(thread_id: str):
    """Get a conversation's metadata (no messages)."""
    cp = _make_checkpointer()
    meta = await cp.load_meta(thread_id)
    if not meta:
        return JSONResponse({"error": "conversation not found"}, status_code=404)
    return meta


@app.delete("/api/conversations/{thread_id}")
async def delete_conversation(thread_id: str):
    """Delete a conversation by thread_id."""
    cp = _make_checkpointer()
    deleted = await cp.delete(thread_id)
    if not deleted:
        return JSONResponse({"error": "conversation not found"}, status_code=404)
    return {"ok": True, "thread_id": thread_id}


@app.patch("/api/conversations/{thread_id}/rename")
async def rename_conversation(thread_id: str, request: Request):
    """Rename a conversation."""
    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        return JSONResponse({"error": "title is required"}, status_code=400)
    cp = _make_checkpointer()
    ok = await cp.update_title(thread_id, title)
    if not ok:
        return JSONResponse({"error": "conversation not found"}, status_code=404)
    return {"ok": True, "title": title}


@app.patch("/api/conversations/{thread_id}/archive")
async def archive_conversation(thread_id: str):
    """Archive a conversation."""
    cp = _make_checkpointer()
    ok = await cp.update_status(thread_id, "archived")
    if not ok:
        return JSONResponse({"error": "conversation not found"}, status_code=404)
    return {"ok": True, "thread_id": thread_id}


@app.patch("/api/conversations/{thread_id}/unarchive")
async def unarchive_conversation(thread_id: str):
    """Unarchive a conversation."""
    cp = _make_checkpointer()
    ok = await cp.update_status(thread_id, "regular")
    if not ok:
        return JSONResponse({"error": "conversation not found"}, status_code=404)
    return {"ok": True, "thread_id": thread_id}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    import uvicorn
    cfg = get_config()
    host = "0.0.0.0"
    port = 20266
    logging.basicConfig(
        level=logging.INFO,
        format="[NanoDeer] %(levelname)s: %(message)s",
    )
    logger.info("NanoDeer API starting on http://%s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
