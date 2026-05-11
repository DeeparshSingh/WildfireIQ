"""Active evacuation orders and alerts from BC Emergency Management."""

from fastapi import APIRouter

from ._envelope import not_implemented

router = APIRouter()


@router.get("/active", summary="All active evacuation orders + alerts in bbox")
async def active() -> dict:
    return not_implemented("bcem_evac_active", target_phase="1")


@router.get("/check", summary="Check evacuation status at a coordinate")
async def check(lat: float, lon: float) -> dict:
    return not_implemented("bcem_evac_check", target_phase="1")
