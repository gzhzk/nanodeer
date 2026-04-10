"""NanoDeer API server — FastAPI application entry point.

Run with:
    uvicorn nanodeer.app.main:app --host 0.0.0.0 --port 20264 --reload
Or:
    python -m nanodeer.app.main
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import run, upload, schedule, threads
from .config import get_app_config
from .models import HealthResponse
from .scheduler import load_existing_jobs

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop lifecycle — load scheduled jobs on startup."""
    log.info("NanoDeer API starting up...")
    load_existing_jobs()
    yield
    log.info("NanoDeer API shutting down...")


app = FastAPI(
    title="NanoDeer API",
    description="Ultra-lightweight AI Agent harness — file upload + cron + streaming.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(run.router)
app.include_router(upload.router)
app.include_router(schedule.router)
app.include_router(threads.router)


@app.get("/health", response_model=HealthResponse, tags=["meta"])
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok", version="0.1.0")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """Run the API server via uvicorn."""
    import uvicorn
    cfg = get_app_config()
    uvicorn.run(
        "nanodeer.app.main:app",
        host=cfg.host,
        port=cfg.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
