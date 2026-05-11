"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from . import __version__
from .routers import aq, climate, evac, fires, firesmart, fwi, risk, weather
from .settings import get_settings


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
    # Phase 1 will wire APScheduler here.
    yield
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
        ],
    )

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
            "phase": "0",
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

    return app


app = create_app()
