"""Type-safe app configuration loaded from environment / .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[3]


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

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

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
