"""APScheduler-based cron scheduler for NanoDeer.

Jobs are stored as JSON files in schedules/ and loaded on startup.
Each job's prompt is run via runner.run_agent when the cron fires.
"""

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore

from .config import get_app_config
from .models import ScheduleItem
from .runner import run_agent
from .storage import ScheduleStorage, UploadStorage

log = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_schedule_storage_global: ScheduleStorage | None = None


def _get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            job_defaults={"coalesce": True, "max_instances": 1},
        )
    return _scheduler


async def _run_scheduled_job(job_id: str, prompt: str, thread_id: str | None) -> None:
    """Execute a scheduled job — called by APScheduler when cron fires."""
    from .models import RunRequest

    log.info(f"[Scheduler] Running job {job_id}: {prompt[:50]}...")

    req = RunRequest(
        prompt=prompt,
        thread_id=thread_id,
        upload_ids=[],
    )

    try:
        result = await run_agent(req, UploadStorage())

        # Update last_run_at, next_run_at, run_count
        storage = get_schedule_storage()
        job = storage.get(job_id)
        if job:
            sched = _get_scheduler()
            next_fire = sched.get_job(job_id)
            storage.update(
                job_id,
                last_run_at=datetime.utcnow().isoformat(),
                next_run_at=next_fire.next_run_time.isoformat() if next_fire and next_fire.next_run_time else None,
                run_count=job.get("run_count", 0) + 1,
            )
        log.info(f"[Scheduler] Job {job_id} completed in {result.duration_ms}ms")
    except Exception as e:
        log.error(f"[Scheduler] Job {job_id} failed: {e}")


def get_schedule_storage() -> ScheduleStorage:
    global _schedule_storage_global
    if _schedule_storage_global is None:
        _schedule_storage_global = ScheduleStorage()
    return _schedule_storage_global


def add_job(name: str, prompt: str, cron: str, thread_id: str | None = None) -> ScheduleItem:
    """Create and register a new cron job."""
    # Save to storage
    entry = get_schedule_storage().create(name, prompt, cron, thread_id)
    job_id = entry["id"]

    # Parse cron and validate
    try:
        trigger = CronTrigger.from_crontab(cron)
    except Exception as e:
        raise ValueError(f"Invalid cron expression: {cron}") from e

    # Register with APScheduler
    scheduler = _get_scheduler()
    scheduler.add_job(
        _run_scheduled_job,
        trigger=trigger,
        args=[job_id, prompt, thread_id],
        id=job_id,
        name=name,
        replace_existing=True,
    )

    # Start scheduler lazily (APScheduler auto-starts when first job fires
    # in a running event loop; for FastAPI the lifespan starts the loop)

    return ScheduleItem(
        id=job_id,
        name=name,
        prompt=prompt,
        cron=cron,
        thread_id=thread_id,
        enabled=True,
        created_at=datetime.fromisoformat(entry["created_at"]),
        next_run_at=None,  # list_jobs() fetches this from APScheduler
    )


def remove_job(job_id: str) -> bool:
    """Remove and delete a cron job."""
    scheduler = _get_scheduler()
    job = scheduler.get_job(job_id)
    if job:
        scheduler.remove_job(job_id)
    return get_schedule_storage().delete(job_id)


def list_jobs() -> list[ScheduleItem]:
    """List all registered schedules with next-run info."""
    storage = get_schedule_storage()
    scheduler = _get_scheduler()
    items = storage.list_all()
    result = []
    for item in items:
        ap_job = scheduler.get_job(item["id"])
        next_run = None
        if ap_job:
            nrt = getattr(ap_job, "next_run_time", None)
            if nrt:
                next_run = datetime.fromtimestamp(nrt.timestamp())
        result.append(ScheduleItem(
            id=item["id"],
            name=item["name"],
            prompt=item["prompt"],
            cron=item["cron"],
            thread_id=item.get("thread_id"),
            enabled=item.get("enabled", True),
            created_at=datetime.fromisoformat(item["created_at"]),
            last_run_at=datetime.fromisoformat(item["last_run_at"]) if item.get("last_run_at") else None,
            next_run_at=next_run,
            run_count=item.get("run_count", 0),
        ))
    return result


def pause_job(job_id: str) -> bool:
    """Pause a job (stop it from firing)."""
    scheduler = _get_scheduler()
    try:
        scheduler.pause_job(job_id)
        get_schedule_storage().update(job_id, enabled=False)
        return True
    except Exception:
        return False


def resume_job(job_id: str) -> bool:
    """Resume a paused job."""
    scheduler = _get_scheduler()
    try:
        scheduler.resume_job(job_id)
        get_schedule_storage().update(job_id, enabled=True)
        return True
    except Exception:
        return False


def load_existing_jobs() -> None:
    """Load all schedules from storage into APScheduler on startup."""
    scheduler = _get_scheduler()
    for item in get_schedule_storage().list_all():
        job_id = item["id"]
        try:
            trigger = CronTrigger.from_crontab(item["cron"])
        except Exception:
            log.warning(f"Skipping invalid cron for job {job_id}: {item['cron']}")
            continue

        scheduler.add_job(
            _run_scheduled_job,
            trigger=trigger,
            args=[job_id, item["prompt"], item.get("thread_id")],
            id=job_id,
            name=item["name"],
            replace_existing=True,
            enabled=item.get("enabled", True),
        )

    if scheduler.get_jobs():
        scheduler.start()
        log.info(f"Loaded {len(scheduler.get_jobs())} scheduled jobs")
