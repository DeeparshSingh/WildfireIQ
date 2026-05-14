"""Air quality realtime + 48h forecast + smoke calendar + health guidance."""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from ..ml.aq_infer import predict_calendar, predict_forecast
from ..paths import GEO_ROOT
from . import _data
from ._envelope import Envelope, Meta

router = APIRouter()


@router.get("/current", summary="Current AQHI + pollutant breakdown")
async def current() -> dict[str, Any]:
    stations = _data.aqhi_current()
    pollutants = _data.aq_pollutants_latest()
    return Envelope[dict](
        data={
            "stations": stations,
            "pollutants": pollutants,
        },
        meta=Meta(
            source="geomet_aqhi + waqi_kamloops",
            attribution="ECCC GeoMet · WAQI / AQICN",
            phase="4",
        ),
    ).model_dump(mode="json")


@router.get("/forecast", summary="48-hour PM2.5 forecast with q10/q50/q90")
async def forecast(hours: int = 48) -> dict[str, Any]:
    payload = predict_forecast()
    if payload is None:
        raise HTTPException(
            503,
            "AQ forecaster artifacts not found. Run `--only open_meteo_aq_archive` "
            "then `uv run python -m wildfireiq_api.ml.train_aq`.",
        )
    return Envelope[dict](
        data=payload,
        meta=Meta(
            source="aq_forecaster_v1",
            attribution="LightGBM quantile, trained on Open-Meteo air quality archive "
            "(92 days hourly) + co-located weather. Per-horizon models for "
            "+1/+3/+6/+12/+24/+36/+48 h.",
            phase="4",
            note=f"issued at {payload['issued_at_utc'][:16]}; quantile bands are q10–q90",
        ),
    ).model_dump(mode="json")


@router.get("/history", summary="Past N days of AQHI readings")
async def history(days: int = 30) -> dict[str, Any]:
    rows = _data.aqhi_history(days=days)
    return Envelope[list](
        data=rows,
        meta=Meta(
            source="geomet_aqhi",
            attribution="ECCC GeoMet · AQHI observations",
            phase="4",
        ),
    ).model_dump(mode="json")


@router.get("/smoke-forecast", summary="ECCC FireWork smoke plume forecast WMS URLs")
async def smoke_forecast() -> dict[str, Any]:
    rows = _data.smoke_forecast_metadata()
    return Envelope[list](
        data=rows,
        meta=Meta(
            source="firework_smoke_forecast",
            attribution="ECCC · RAQDPS-FW Wildfire Smoke (via MSC GeoMet WMS)",
            phase="4",
            note="URLs are WMS GetMap requests — pass directly to Cesium WebMapServiceImageryProvider",
        ),
    ).model_dump(mode="json")


@router.get("/calendar", summary="Per-day max PM2.5 + AQHI for the last N days (smoke event heatmap)")
async def calendar(days: int = 90) -> dict[str, Any]:
    payload = predict_calendar(days=days)
    if payload is None:
        raise HTTPException(503, "AQ hourly archive not available")
    return Envelope[dict](
        data=payload,
        meta=Meta(
            source="aq_hourly_kamloops",
            attribution="Open-Meteo CAMS air quality · daily aggregation",
            phase="4",
        ),
    ).model_dump(mode="json")


@router.get("/health-guidance", summary="Health-band guidance for the current AQHI")
async def health_guidance() -> dict[str, Any]:
    path: Path = GEO_ROOT / "health_guidance.json"
    if not path.exists():
        raise HTTPException(503, "guidance config missing")
    payload = json.loads(path.read_text())
    return Envelope[dict](
        data=payload,
        meta=Meta(
            source="health_guidance.json",
            attribution=payload.get("source", "Health Canada AQHI"),
            phase="4",
        ),
    ).model_dump(mode="json")
