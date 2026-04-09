"""GET /threads — thread history endpoints."""

from fastapi import APIRouter, HTTPException

from ..models import ThreadListResponse, ThreadSummary
from ..storage import ThreadStorage

router = APIRouter(prefix="/threads", tags=["threads"])

_storage: ThreadStorage | None = None


def _get_storage() -> ThreadStorage:
    global _storage
    if _storage is None:
        _storage = ThreadStorage()
    return _storage


@router.get("/", response_model=ThreadListResponse)
async def list_threads() -> ThreadListResponse:
    """List recent threads (conversation sessions)."""
    storage = _get_storage()
    threads = storage.list_threads(limit=20)
    return ThreadListResponse(
        threads=[
            ThreadSummary(
                thread_id=t["thread_id"],
                created_at=t["created_at"],
                updated_at=t["updated_at"],
                message_count=t["message_count"],
                preview=t["preview"],
            )
            for t in threads
        ]
    )


@router.get("/{thread_id}")
async def get_thread_history(thread_id: str) -> dict:
    """Get the run history for a specific thread."""
    storage = _get_storage()
    history = storage.get_history(thread_id, limit=50)
    if not history:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"thread_id": thread_id, "history": history}
