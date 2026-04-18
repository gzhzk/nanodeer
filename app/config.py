"""App-level configuration for NanoDeer API server.

App-level config (HTTP host/port/storage paths) is independent from
harness-level config (LLM providers, sandbox, memory). They are composed
at runtime via the runner, not via inheritance.

Principle: app layer does not subclass harness config. Each layer has
its own config scope, keeping concerns cleanly separated.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class AppConfig(BaseSettings):
    """NanoDeer API server configuration.

    Fields here are HTTP-layer concerns only (host/port/storage paths).
    LLM provider, model, sandbox, and memory config live in harness/config.py.
    """

    host: str = "0.0.0.0"
    port: int = 20264
    # Upload storage: ~/.nanodeer/app/uploads/{upload_id}/{filename}
    upload_dir: Path = Field(default=Path.home() / ".nanodeer" / "app" / "uploads")
    # Schedule JSON files: ~/.nanodeer/app/schedules/{job_id}.json
    schedule_dir: Path = Field(default=Path.home() / ".nanodeer" / "app" / "schedules")
    # Thread history: ~/.nanodeer/app/history/{thread_id}/history.jsonl
    thread_dir: Path = Field(default=Path.home() / ".nanodeer" / "app" / "history")

    class Config:
        env_prefix = "NANODEER_APP_"


_app_config: AppConfig | None = None


def get_app_config() -> AppConfig:
    """Get the app config singleton, creating dirs on first call."""
    global _app_config
    if _app_config is None:
        _app_config = AppConfig()
        for dir_field in ("upload_dir", "schedule_dir", "thread_dir"):
            getattr(_app_config, dir_field).mkdir(parents=True, exist_ok=True)
    return _app_config
