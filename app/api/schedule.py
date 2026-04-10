"""CRUD /schedules — cron job management endpoints."""

from datetime import datetime

from fastapi import APIRouter, HTTPException

from ..models import ScheduleCreate, ScheduleItem, ScheduleListResponse
from ..scheduler import (
    add_job, get_schedule_storage, list_jobs, pause_job, remove_job, resume_job,
)
from ..storage import ScheduleStorage

router = APIRouter(prefix="/schedules", tags=["schedules"])


@router.post("/", response_model=ScheduleItem, status_code=201)
async def create_schedule(req: ScheduleCreate) -> ScheduleItem:
    """Create a new scheduled job.

    The job will run the `prompt` on the schedule defined by `cron`
    (standard crontab format, e.g. "0 9 * * *" = every day at 9am UTC).

    Returns the created schedule with its ID and next fire time.
    """
    try:
        return add_job(name=req.name, prompt=req.prompt, cron=req.cron, thread_id=req.thread_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=ScheduleListResponse)
async def list_schedules() -> ScheduleListResponse:
    """List all scheduled jobs with their next fire times."""
    return ScheduleListResponse(schedules=list_jobs())


@router.get("/{job_id}", response_model=ScheduleItem)
async def get_schedule(job_id: str) -> ScheduleItem:
    """Get a specific schedule by ID."""
    storage = get_schedule_storage()
    job = storage.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Schedule not found")

    from ..scheduler import _get_scheduler
    scheduler = _get_scheduler()
    ap_job = scheduler.get_job(job_id)
    next_run = None
    if ap_job and ap_job.next_run_time:
        next_run = datetime.fromtimestamp(ap_job.next_run_time.timestamp())

    return ScheduleItem(
        id=job["id"],
        name=job["name"],
        prompt=job["prompt"],
        cron=job["cron"],
        thread_id=job.get("thread_id"),
        enabled=job.get("enabled", True),
        created_at=datetime.fromisoformat(job["created_at"]),
        last_run_at=datetime.fromisoformat(job["last_run_at"]) if job.get("last_run_at") else None,
        next_run_at=next_run,
        run_count=job.get("run_count", 0),
    )


@router.delete("/{job_id}", status_code=204)
async def delete_schedule(job_id: str) -> None:
    """Delete a scheduled job."""
    if not remove_job(job_id):
        raise HTTPException(status_code=404, detail="Schedule not found")


@router.post("/{job_id}/pause", response_model=ScheduleItem)
async def pause_schedule(job_id: str) -> ScheduleItem:
    """Pause a scheduled job (stops it from firing)."""
    if not pause_job(job_id):
        raise HTTPException(status_code=404, detail="Schedule not found")
    return await get_schedule(job_id)


@router.post("/{job_id}/resume", response_model=ScheduleItem)
async def resume_schedule(job_id: str) -> ScheduleItem:
    """Resume a paused scheduled job."""
    if not resume_job(job_id):
        raise HTTPException(status_code=404, detail="Schedule not found")
    return await get_schedule(job_id)
