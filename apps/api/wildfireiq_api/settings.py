"""Type-safe app configuration loaded from the environment or a `.env` file.

Configuration only. The third-party API keys are not here: they are entered
in the app's Settings panel and held by `keys.py`, so a reader never needs
a file on disk to unlock a feature."""

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
    # The OpenRouter key lives in the runtime key store (keys.py), entered
    # through the Settings panel. Without it the assistant endpoints stay
    # mounted but report `configured: false`, so the frontend can offer the
    # Settings panel instead of failing a request.
    assistant_enabled: bool = Field(default=True)
    assistant_model: str = Field(default="z-ai/glm-5.3-flash")
    # Budget caps. A step is one model turn; a turn that asks for tools is
    # followed by another. Five steps is generous — the observed ceiling on
    # real questions is three — and it bounds the worst case if the model
    # ever loops asking for the same tool.
    assistant_max_steps: int = Field(default=5, ge=1, le=10)
    assistant_max_tool_calls: int = Field(default=12, ge=1, le=40)
    assistant_timeout_s: float = Field(default=90.0)
    # Output budget per model turn. GLM 5.3 Flash is a reasoning model: its
    # private thinking shares this allowance with the answer, so a turn that
    # thinks hard about a forecast can spend the lot and return nothing.
    # 3,000 leaves ample headroom for both; at $0.25/M output the ceiling
    # costs under a tenth of a cent even when fully used.
    assistant_max_output_tokens: int = Field(default=3000, ge=500)
    # How hard the model thinks before answering. OpenRouter reserves the
    # reasoning allowance first and writes the answer from what is left, so
    # this is the single biggest lever on both latency and the risk of a
    # turn thinking itself out of room. "low" keeps tool selection sharp on
    # the evaluation suite while cutting the slowest answers roughly in
    # half. "none" disables thinking; "high" is for debugging a hard case.
    assistant_reasoning_effort: str = Field(default="low")
    # Attribution headers OpenRouter shows on its dashboards. Harmless if
    # the app is never public.
    assistant_referer: str = Field(default="https://github.com/DeeparshSingh/WildfireIQ")
    assistant_title: str = Field(default="WildfireIQ Kamloops")

    # ── Assistant abuse + spend limits ───────────────────────────────
    # This is the only endpoint whose cost is money rather than CPU, and
    # the platform has no accounts to bill it to, so the limits are the
    # access control. See assistant/guard.py.
    assistant_rate_per_minute: int = Field(default=4, ge=1)
    assistant_rate_per_hour: int = Field(default=30, ge=1)
    assistant_max_concurrent: int = Field(default=4, ge=1)
    # A rolling 24-hour ceiling in USD. At the measured ~$0.003 for a
    # researched answer, $2 is roughly 600 questions a day — generous for a
    # research deployment, and a hard stop against anything pathological.
    assistant_daily_cost_limit_usd: float = Field(default=2.0, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
