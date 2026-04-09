"""App runner — FastAPI adapter on top of NanoEngine.

Thin HTTP layer: converts FastAPI request → NanoEngine.run() → response.
All agent complexity lives in harness/engine.py.
"""

from .models import RunRequest, RunResponse
from .storage import ThreadStorage

# Global engine instance (initialized lazily)
_engine = None


def _get_engine():
    """Get or create the global NanoEngine instance."""
    global _engine
    if _engine is None:
        from harness.engine import NanoEngine
        from harness.config import get_config

        _engine = NanoEngine(get_config())
    return _engine


async def run_agent(req: RunRequest, upload_storage) -> RunResponse:
    """Run the agent with the given request.

    Args:
        req: The run request with prompt, optional thread_id, and upload_ids.
        upload_storage: UploadStorage instance to resolve uploaded files.

    Returns:
        RunResponse with the agent's final message and metadata.
    """
    # Resolve uploaded files
    uploaded_files: list[dict] = []
    for uid in req.upload_ids:
        meta = upload_storage.get(uid)
        if not meta:
            continue
        files = upload_storage.list_files(uid)
        for f in files:
            content_bytes = f.read_bytes()
            try:
                content = content_bytes.decode("utf-8")
                is_text = True
            except Exception:
                content = f"Binary file ({len(content_bytes)} bytes)"
                is_text = False

            uploaded_files.append({
                "name": f.name,
                "content": content if is_text else "",
                "mime_type": meta.get("content_type", "application/octet-stream"),
                "_binary": not is_text,
            })

    # Delegate to engine
    engine = _get_engine()
    result = await engine.run(
        prompt=req.prompt,
        thread_id=req.thread_id,
        system_hint=req.system_hint,
        uploaded_files=uploaded_files,
        model=req.model,
    )

    # Persist to thread history
    thread_storage = ThreadStorage()
    thread_storage.append(result.thread_id, {
        "message": result.message[:500],
        "artifacts": result.artifacts,
        "tool_calls": result.tool_calls,
        "duration_ms": result.duration_ms,
    })

    return RunResponse(
        thread_id=result.thread_id,
        message=result.message,
        artifacts=result.artifacts,
        tool_calls=result.tool_calls,
        duration_ms=result.duration_ms,
    )
