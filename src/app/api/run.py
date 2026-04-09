"""POST /run — core agent invocation endpoint."""

from fastapi import APIRouter, HTTPException

from ..models import RunRequest, RunResponse
from ..runner import run_agent
from ..storage import UploadStorage

router = APIRouter(prefix="/run", tags=["agent"])


@router.post("/", response_model=RunResponse)
async def run(req: RunRequest) -> RunResponse:
    """Run the NanoDeer agent with a prompt.

    The agent will use all available tools (web search, file read/write,
    bash, Python execution, subagents, etc.) to fulfill the request.

    If `upload_ids` is provided, files from prior /upload calls will be
    attached and accessible to the agent.

    The `thread_id` can be provided to continue a multi-turn conversation.
    """
    try:
        upload_storage = UploadStorage()
        return await run_agent(req, upload_storage)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Missing dependency: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
