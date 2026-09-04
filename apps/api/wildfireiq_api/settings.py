"""Type-safe app configuration loaded from environment / .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from . import constants

REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve_sqlite_url(url: str) -> str:
    """Rewrite `sqlite+aiosqlite:///./data/...` to an absolute path under repo root."""
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    for prefix in prefixes:
        if url.startswith(prefix):
            path_str = url[len(prefix) :]
            p = Path(path_str)
            if not p.is_absolute():
                p = (REPO_ROOT / p).resolve()
            return f"{prefix}{p}"
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Upstream API keys (ingest degrades gracefully when unset) ──
    firms_map_key: str = Field(default="", description="NASA FIRMS API key")
    waqi_token: str = Field(default="", description="WAQI / AQICN token")

    # ── App config ───────────────────────────────────────────────────
    database_url: str = Field(default=f"sqlite+aiosqlite:///{REPO_ROOT / 'data' / 'wildfireiq.db'}")

    @field_validator("database_url", mode="after")
    @classmethod
    def _abs_db_url(cls, v: str) -> str:
        return _resolve_sqlite_url(v)

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # Run APScheduler in-process so every cron cadence actually fires.
    # Set SCHEDULER_ENABLED=false in .env to disable (e.g. for CI / tests).
    scheduler_enabled: bool = Field(default=True)
    # Run every recurring job once at startup if its last successful run is
    # older than the configured threshold. Ensures cold-start = fresh data.
    startup_refresh_minutes: int = Field(default=30)

    # ── Region (Thompson-Okanagan canonical bbox) ────────────────────
    # Defaults come from constants.py so the numbers live in exactly one
    # place; these stay overridable by env for anyone re-pointing the
    # climate module at a different region.
    bbox_west: float = constants.BBOX_WEST
    bbox_south: float = constants.BBOX_SOUTH
    bbox_east: float = constants.BBOX_EAST
    bbox_north: float = constants.BBOX_NORTH

    # ── Kamloops centroid for default queries ────────────────────────
    kamloops_lat: float = constants.KAMLOOPS_LAT
    kamloops_lon: float = constants.KAMLOOPS_LON

    # ── Assistant (OpenRouter-hosted GLM) ────────────────────────────
    # With no key the assistant endpoints stay mounted but report
    # `configured: false`, so the frontend can hide its launcher instead
    # of failing a request. Nothing else in the app depends on it.
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    assistant_enabled: bool = Field(default=True)
    assistant_model: str = Field(default="z-ai/glm-5.3-flash")
    # Budget caps. A step is one model turn; a turn that asks for tools is
    # followed by another. Five steps is generous — the observed ceiling on
    # real questions is three — and it bounds the worst case if the model
    # ever loops asking for the same tool.
    assistant_max_steps: int = Field(default=5, ge=1, le=10)
    assistant_max_tool_calls: int = Field(default=12, ge=1, le=40)
    assistant_timeout_s: float = Field(default=90.0)
    # Attribution headers OpenRouter shows on its dashboards. Harmless if
    # the app is never public.
    assistant_referer: str = Field(default="https://github.com/DeeparshSingh/WildfireIQ")
    assistant_title: str = Field(default="WildfireIQ Kamloops")


@lru_cache
def get_settings() -> Settings:
    return Settings()
