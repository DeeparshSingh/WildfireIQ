"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.staticfiles import StaticFiles

from . import __version__
from .assistant.router import router as assistant_router
from .db import init_db
from .owner import admin_token, control
from .paths import REPO_ROOT
from .routers import admin, aq, climate, evac, fires, firesmart, fwi, risk, weather
from .routers.ownership import router as ownership_router
from .routers.settings import router as settings_router
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


class OwnerControlMiddleware(BaseHTTPMiddleware):
    """Refuses API requests while the owner has the deployment paused.

    The check is a dictionary lookup against state already in memory, so it
    costs nothing per request. `/healthz` and `/api/ownership` always answer,
    so a paused deployment can still be diagnosed from outside and the owner
    can confirm the pause landed.
    """

    async def dispatch(self, request: Request, call_next):
        refusal = control.blocks(request.url.path, request.method)
        if refusal is None:
            return await call_next(request)
        return JSONResponse(
            status_code=503,
            content={"detail": refusal, "state": control.state},
            headers={"Retry-After": "300", "Cache-Control": "no-store"},
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
        # Don't override an already-set header (e.g. CSV downloads, SSE).
        if response.headers.get("cache-control"):
            return response
        # The assistant's answers are per-question and its stream must not
        # be held anywhere. Never cache them.
        if path.startswith("/api/assistant"):
            response.headers["cache-control"] = "no-store"
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
    settings = get_settings()
    # Refresh anything stale before serving — fires the cron jobs that would
    # otherwise wait for their next scheduled tick. Backgrounded so the
    # event loop is free to accept the first request immediately.
    refresh_task = asyncio.create_task(refresh_stale_jobs(settings.startup_refresh_minutes))
    if settings.scheduler_enabled:
        start_scheduler()
    else:
        log.info("scheduler.disabled_via_settings")

    # Owner control: read any standing command, report who this deployment
    # answers to, and start polling the owner's URL if one is configured.
    control.reload()
    health = control.health()
    log.info(
        "owner",
        owner=health.owner,
        key_fingerprint=health.fingerprint,
        state=health.state,
    )
    for problem in health.problems:
        log.warning("owner.problem", detail=problem)
    token = admin_token(settings.admin_token)
    if not settings.admin_token:
        # Printed once so the owner can find it without reading a file. It is
        # the only way an unattended first boot could tell anyone the token.
        log.info("owner.admin_token", token=token, hint="also in data/runtime/owner.json")

    async def poll_owner_url() -> None:
        while True:
            await control.refresh_remote(settings.owner_control_url)
            await asyncio.sleep(settings.owner_control_poll_seconds)

    poll_task = asyncio.create_task(poll_owner_url()) if settings.owner_control_url else None

    yield
    refresh_task.cancel()
    if poll_task is not None:
        poll_task.cancel()
    stop_scheduler()
    log.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    log = structlog.get_logger()
    app = FastAPI(
        title="WildfireIQ API",
        version=__version__,
        description=(
            "Backend for the WildfireIQ Kamloops platform — wildfire risk, air quality, "
            "preparedness, and climate trend data for the Thompson-Okanagan region."
        ),
        lifespan=lifespan,
        openapi_tags=[
            {"name": "system", "description": "Health, version, metadata."},
            {
                "name": "fires",
                "description": "Active + historical fire incidents and FIRMS hotspots.",
            },
            {"name": "risk", "description": "AI-derived wildfire risk grid."},
            {"name": "weather", "description": "Current + forecast weather for Kamloops."},
            {"name": "fwi", "description": "Fire Weather Index station readings."},
            {"name": "aq", "description": "Air quality realtime + 48-hour forecast."},
            {"name": "evac", "description": "Active evacuation orders and alerts."},
            {"name": "firesmart", "description": "Personalized FireSmart checklist."},
            {"name": "climate", "description": "Historical climate + projections."},
            {"name": "admin", "description": "Trigger ingest jobs + inspect runs."},
            {
                "name": "ownership",
                "description": "Who owns this deployment, and its service state.",
            },
            {"name": "settings", "description": "Which API keys the server holds."},
            {
                "name": "assistant",
                "description": "Tool-using assistant over the platform's own data.",
            },
        ],
    )

    app.add_middleware(CacheControlMiddleware)
    # Outermost of the two, so a paused deployment refuses before any work.
    app.add_middleware(OwnerControlMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        # PUT is what the Settings panel uses to store API keys. It was missing
        # here, so the browser's preflight got a 400 and the panel reported the
        # API unreachable while GETs from the same page worked.
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, Any]:
        return {
            "ok": True,
            "version": __version__,
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
    app.include_router(assistant_router, prefix="/api/assistant", tags=["assistant"])
    app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
    app.include_router(ownership_router, prefix="/api/ownership", tags=["ownership"])

    # ── the built web app, served from this same origin ──────────────────
    #
    # With the browser and the API on one origin, CORS does not apply at all:
    # no list of allowed origins to keep in step with a domain name, and no
    # preflight to get wrong. `./start.sh --serve` builds apps/web/dist and
    # this picks it up. In development the Vite server serves the app instead
    # and the CORS list above covers those two localhost origins.
    dist = REPO_ROOT / "apps" / "web" / "dist"
    if settings.serve_web and (dist / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
        if (dist / "cesium").is_dir():
            app.mount("/cesium", StaticFiles(directory=dist / "cesium"), name="cesium")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> Response:
            """Serve a real file when one exists, else index.html.

            The app is a single-page application: /climate and /air-quality are
            client-side routes with no file behind them, so a deep link or a
            refresh has to come back as index.html rather than a 404.
            """
            candidate = (dist / path).resolve()
            if path and dist in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

        log.info("web.served_from_api", directory=str(dist))

    return app


app = create_app()
