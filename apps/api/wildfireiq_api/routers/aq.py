"""Air quality realtime + 48h forecast (forecaster lands in Phase 3)."""

from typing import Any

from fastapi import APIRouter

from . import _data
from ._envelope import Envelope, Meta
from ._envelope import not_implemented

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
            phase="1",
        ),
    ).model_dump(mode="json")


@router.get("/forecast", summary="48-hour AQ forecast (PM2.5 with q10/q50/q90) — Phase 3")
async def forecast(hours: int = 48) -> dict[str, Any]:
    return not_implemented("aq_forecaster_v1", target_phase="3")


@router.get("/history", summary="Past N days of AQHI readings")
async def history(days: int = 30) -> dict[str, Any]:
    rows = _data.aqhi_history(days=days)
    return Envelope[list](
        data=rows,
        meta=Meta(
            source="geomet_aqhi",
            attribution="ECCC GeoMet · AQHI observations",
            phase="1",
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
            phase="1",
            note="URLs are WMS GetMap requests — pass directly to Cesium WebMapServiceImageryProvider",
        ),
    ).model_dump(mode="json")
