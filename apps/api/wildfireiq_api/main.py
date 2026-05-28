"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from . import __version__
from .db import init_db
from .routers import admin, aq, climate, evac, fires, firesmart, fwi, risk, weather
from .scheduler import refresh_stale_jobs, start_scheduler, stop_scheduler
from .settings import get_settings

# Historical / static endpoints can cache longer — they only change when
# an overnight ingest job rewrites the underlying parquet.
_LONG_CACHE_PREFIXES = (
    "/api/climate/seasonal",
    "/api/climate/trends",
    "/api/climate/ribbon",
    "/api/climate/projection",
    "/api/climate/projections-all",
    "/api/climate/fwi-projection",
    "/api/firesmart/checklist",
    "/api/firesmart/achievements",
    "/api/firesmart/neighbourhoods",
    "/api/aq/health-guidance",
    "/api/aq/calendar",
    "/api/fires/historical",
)


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Tag responses with sensible Cache-Control headers.

    - GET /api/*  → public, max-age=60       (most live endpoints)
    - Long-lived endpoints (above)  → public, max-age=300, s-maxage=600
    - Everything else               → no header (FastAPI defaults)
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        if request.method != "GET":
            return response
        path = request.url.path
        if not path.startswith("/api/"):
            return response
        # Don't override an already-set header (e.g. CSV downloads).
        if response.headers.get("cache-control"):
            return response
        if any(path.startswith(p) for p in _LONG_CACHE_PREFIXES):
            response.headers["cache-control"] = "public, max-age=300, s-maxage=600"
        else:
            response.headers["cache-control"] = "public, max-age=60"
        return response


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    log = structlog.get_logger()
    log.info("startup", version=__version__)
    await init_db()
    # DuckDB warm-up: open the analytics DB once at startup so the first
    # request doesn't pay the cold-open cost (~400 ms → ~20 ms).
    try:
        import duckdb

        settings_for_warmup = get_settings()
        con = duckdb.connect(settings_for_warmup.duckdb_path, read_only=False)
        con.execute("SELECT 1").fetchall()
        con.close()
        log.info("duckdb.warmup.ok")
    except Exception as exc:
        log.warning("duckdb.warmup.skip", error=str(exc))
    settings = get_settings()
    # Refresh anything stale before serving — fires the cron jobs that would
    # otherwise wait for their next scheduled tick. Backgrounded so the
    # event loop is free to accept the first request immediately.
    refresh_task = asyncio.create_task(
        refresh_stale_jobs(settings.startup_refresh_minutes)
    )
    if settings.scheduler_enabled:
        start_scheduler()
    else:
        log.info("scheduler.disabled_via_settings")
    yield
    refresh_task.cancel()
    stop_scheduler()
    log.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="WildfireIQ API",
        version=__version__,
        description=(
            "Backend for the WildfireIQ Kamloops platform — wildfire risk, air quality, "
            "preparedness, and climate trend data for the Thompson-Okanagan region."
        ),
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        openapi_tags=[
            {"name": "system", "description": "Health, version, metadata."},
            {"name": "fires", "description": "Active + historical fire incidents and FIRMS hotspots."},
            {"name": "risk", "description": "AI-derived wildfire risk grid (Phase 3)."},
            {"name": "weather", "description": "Current + forecast weather for Kamloops."},
            {"name": "fwi", "description": "Fire Weather Index station readings."},
            {"name": "aq", "description": "Air quality realtime + 48h forecast (Phase 3)."},
            {"name": "evac", "description": "Active evacuation orders and alerts."},
            {"name": "firesmart", "description": "Personalized FireSmart checklist (Phase 5)."},
            {"name": "climate", "description": "Historical climate + projections (Phase 6)."},
            {"name": "admin", "description": "Trigger ingest jobs + inspect runs."},
        ],
    )

    app.add_middleware(CacheControlMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, Any]:
        return {
            "ok": True,
            "version": __version__,
            "phase": "1",
            "bbox": [
                settings.bbox_west,
                settings.bbox_south,
                settings.bbox_east,
                settings.bbox_north,
            ],
        }

    app.include_router(fires.router, prefix="/api/fires", tags=["fires"])
    app.include_router(risk.router, prefix="/api/risk", tags=["risk"])
    app.include_router(weather.router, prefix="/api/weather", tags=["weather"])
    app.include_router(fwi.router, prefix="/api/fwi", tags=["fwi"])
    app.include_router(aq.router, prefix="/api/aq", tags=["aq"])
    app.include_router(evac.router, prefix="/api/evac", tags=["evac"])
    app.include_router(firesmart.router, prefix="/api/firesmart", tags=["firesmart"])
    app.include_router(climate.router, prefix="/api/climate", tags=["climate"])
    app.include_router(admin.router, prefix="/api/admin", tags=["admin"])

    return app


app = create_app()
