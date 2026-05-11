"""Active + historical fire incidents and FIRMS hotspots. Phase 1 implementation."""

from fastapi import APIRouter

from ._envelope import not_implemented

router = APIRouter()


@router.get("/current", summary="Current active BC fires within bbox")
async def current() -> dict:
    return not_implemented("databc_fires_current", target_phase="1")


@router.get("/hotspots", summary="NASA FIRMS satellite hotspots (last N hours)")
async def hotspots(since: str = "24h") -> dict:
    return not_implemented("firms_hotspots", target_phase="1")


@router.get("/historical", summary="Historical BC fires for a given year")
async def historical(year: int = 2023) -> dict:
    return not_implemented("databc_fires_historical", target_phase="1")
