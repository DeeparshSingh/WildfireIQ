"""AI wildfire risk grid (Phase 3 model)."""

from fastapi import APIRouter

from ._envelope import not_implemented

router = APIRouter()


@router.get("/today", summary="Risk score for a single H3 cell on today's date")
async def today(cell: str | None = None) -> dict:
    return not_implemented("wildfire_risk_today", target_phase="3")


@router.get("/grid", summary="Full risk grid for the Thompson-Okanagan")
async def grid(date: str | None = None) -> dict:
    return not_implemented("wildfire_risk_grid", target_phase="3")
