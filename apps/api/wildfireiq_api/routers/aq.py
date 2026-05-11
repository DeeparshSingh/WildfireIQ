"""Air quality realtime + 48h forecast (forecaster lands in Phase 3)."""

from fastapi import APIRouter

from ._envelope import not_implemented

router = APIRouter()


@router.get("/current", summary="Current AQHI for Kamloops")
async def current() -> dict:
    return not_implemented("geomet_aqhi_current", target_phase="1")


@router.get("/forecast", summary="48-hour AQ forecast (PM2.5 with q10/q50/q90)")
async def forecast(hours: int = 48) -> dict:
    return not_implemented("aq_forecaster_v1", target_phase="3")


@router.get("/history", summary="Past N days of AQHI readings")
async def history(days: int = 30) -> dict:
    return not_implemented("geomet_aqhi_history", target_phase="1")
