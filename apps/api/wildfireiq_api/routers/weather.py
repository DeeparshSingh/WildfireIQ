"""Current + forecast weather for Kamloops (Open-Meteo HRDPS in Phase 1)."""

from fastapi import APIRouter

from ._envelope import not_implemented

router = APIRouter()


@router.get("/current", summary="Current weather snapshot for Kamloops")
async def current() -> dict:
    return not_implemented("open_meteo_current", target_phase="1")


@router.get("/forecast", summary="Hourly weather forecast")
async def forecast(hours: int = 72) -> dict:
    return not_implemented("open_meteo_forecast", target_phase="1")
