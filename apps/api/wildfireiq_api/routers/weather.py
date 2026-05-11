"""Current + forecast weather for Kamloops (Open-Meteo HRDPS)."""

from typing import Any

from fastapi import APIRouter

from . import _data
from ._envelope import Envelope, Meta

router = APIRouter()


@router.get("/current", summary="Current weather snapshot for Kamloops")
async def current() -> dict[str, Any]:
    snap = _data.weather_current()
    return Envelope[dict | None](
        data=snap,
        meta=Meta(
            source="open_meteo_kamloops",
            attribution="Open-Meteo · ECCC GEM-HRDPS",
            phase="1",
        ),
    ).model_dump(mode="json")


@router.get("/forecast", summary="Hourly weather forecast")
async def forecast(hours: int = 72) -> dict[str, Any]:
    rows = _data.weather_forecast(hours=hours)
    return Envelope[list](
        data=rows,
        meta=Meta(
            source="open_meteo_kamloops",
            attribution="Open-Meteo · GEM-HRDPS continental",
            phase="1",
        ),
    ).model_dump(mode="json")
