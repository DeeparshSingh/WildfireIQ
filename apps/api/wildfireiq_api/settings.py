"""Type-safe app configuration loaded from environment / .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve_sqlite_url(url: str) -> str:
    """Rewrite `sqlite+aiosqlite:///./data/...` to an absolute path under repo root."""
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    for prefix in prefixes:
        if url.startswith(prefix):
            path_str = url[len(prefix):]
            p = Path(path_str)
            if not p.is_absolute():
                p = (REPO_ROOT / p).resolve()
            return f"{prefix}{p}"
    return url


def _resolve_path(p: str) -> str:
    path = Path(p)
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return str(path)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Required for Phase 1+ ingestion (Phase 0 tolerates missing) ──
    firms_map_key: str = Field(default="", description="NASA FIRMS API key")
    waqi_token: str = Field(default="", description="WAQI / AQICN token")

    # ── App config ───────────────────────────────────────────────────
    database_url: str = Field(default=f"sqlite+aiosqlite:///{REPO_ROOT / 'data' / 'wildfireiq.db'}")
    duckdb_path: str = Field(default=str(REPO_ROOT / "data" / "analytics.duckdb"))

    @field_validator("database_url", mode="after")
    @classmethod
    def _abs_db_url(cls, v: str) -> str:
        return _resolve_sqlite_url(v)

    @field_validator("duckdb_path", mode="after")
    @classmethod
    def _abs_duckdb_path(cls, v: str) -> str:
        return _resolve_path(v)

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
    bbox_west: float = -121.5
    bbox_south: float = 50.0
    bbox_east: float = -118.5
    bbox_north: float = 51.5

    # ── Kamloops centroid for default queries ────────────────────────
    kamloops_lat: float = 50.6745
    kamloops_lon: float = -120.3273


@lru_cache
def get_settings() -> Settings:
    return Settings()
