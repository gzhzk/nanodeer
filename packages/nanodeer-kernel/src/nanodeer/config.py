"""Configuration schema for NanoDeer harness.

Supports multiple LLM providers with auto-detection.
Inspired by nanobot's Provider pattern.
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file for development
# Search upward from this file's location for .env
from pathlib import Path as _P
_env = _P(__file__).resolve().parents[3] / ".env"
load_dotenv(_env)


def _resolve_env_vars(value: Any) -> Any:
    """Recursively resolve environment variables in config values.

    Supports $VAR and ${VAR} syntax.
    """
    ENV_VAR_PATTERN = re.compile(r'\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?')

    def replace_env_var(match: re.Match) -> str:
        var_name = match.group(1)
        return os.getenv(var_name, match.group(0))

    if isinstance(value, str):
        return ENV_VAR_PATTERN.sub(replace_env_var, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


def _load_yaml_config() -> dict:
    """Load config from config.yaml with env var resolution."""
    paths = [
        Path("config.yaml"),
        Path(__file__).parent.parent.parent / "config.yaml",
        Path.cwd() / "config.yaml",
    ]

    config_path = os.getenv("NANODEER_CONFIG_PATH")
    if config_path:
        paths.insert(0, Path(config_path))

    for path in paths:
        if path.exists():
            with open(path) as f:
                config = yaml.safe_load(f)
            return _resolve_env_vars(config)

    return {}


# ============================================================================
# Config Models
# ============================================================================


class Base(BaseModel):
    """Base model with common config."""

    model_config = ConfigDict(populate_by_name=True)


class ProviderConfig(Base):
    """LLM provider configuration."""

    api_key: str = ""
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None


class AgentsDefaults(Base):
    """Default agent configuration."""

    model: str = "MiniMax-M2.7"
    provider: str = "minimax"  # Provider must be explicitly specified
    max_tokens: int = 8192
    temperature: float = 0.1


class AgentsConfig(Base):
    """Agent configuration."""

    defaults: AgentsDefaults = Field(default_factory=AgentsDefaults)


class SandboxConfig(Base):
    """Sandbox configuration."""

    use: str = "nanodeer.sandbox.docker:DockerSandboxProvider"
    image: str = "nanodeer/sandbox:latest"
    container_prefix: str = "nanodeer-sandbox"
    network_mode: str = "none"  # "none"=no network, "bridge"=with network, "host"=host network
    base_path: Path | None = None  # Defaults to thread.storage_path if None


class SubagentsConfig(Base):
    """Subagents configuration."""

    timeout_seconds: int = 900
    max_concurrent: int = 3


class MemoryConfig(Base):
    """Memory configuration (placeholder for future use)."""

    enabled: bool = True


class ThreadConfig(Base):
    """Thread storage configuration."""

    storage_path: Path = Field(default=Path.home() / ".nanodeer" / "threads")
    checkpointer_type: str = "file"


class SecurityConfig(Base):
    """Security configuration."""

    mode: str = "default"


class HarnessConfig(BaseSettings):
    """Root configuration for NanoDeer."""

    model_config = SettingsConfigDict(
        env_prefix="NANODEER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    # Config sections
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    subagents: SubagentsConfig = Field(default_factory=SubagentsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    thread: ThreadConfig = Field(default_factory=ThreadConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    log_level: str = "info"

    # Provider configs stored as extra fields (populated by from_yaml)

    @classmethod
    def from_yaml(cls) -> "HarnessConfig":
        """Load configuration from config.yaml."""
        yaml_config = _load_yaml_config()
        config_dict = {}

        # Extract standard sections
        for section in ["agents", "sandbox", "subagents", "memory", "thread", "security", "log_level"]:
            if section in yaml_config:
                config_dict[section] = yaml_config[section]

        # Extract provider configs (anything not a standard section)
        standard_sections = {
            "agents", "sandbox", "subagents", "memory", "thread",
            "security", "log_level", "providers"
        }
        for key, value in yaml_config.items():
            if key not in standard_sections and isinstance(value, dict):
                config_dict[key] = value

        inst = cls(**config_dict)
        # Expand ~ in thread storage path (Path field default_factory doesn't auto-expand)
        inst.thread.storage_path = inst.thread.storage_path.expanduser()
        return inst

    def get_provider_config(self, name: str) -> ProviderConfig | None:
        """Get provider config by name."""
        # Check extra fields (from extra="allow")
        extra = getattr(self, "__pydantic_extra__", None)
        if extra and name in extra:
            return ProviderConfig(**extra[name])
        return None


# Global config instance
_config: HarnessConfig | None = None


def get_config() -> HarnessConfig:
    """Get the global config instance (lazy loading from config.yaml)."""
    global _config
    if _config is None:
        _config = HarnessConfig.from_yaml()
        _config.thread.storage_path.mkdir(parents=True, exist_ok=True)
    return _config


def reset_config() -> None:
    """Reset the global config (useful for testing)."""
    global _config
    _config = None