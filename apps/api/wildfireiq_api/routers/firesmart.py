"""Personalized FireSmart checklist (Phase 5)."""

from fastapi import APIRouter

from ._envelope import not_implemented

router = APIRouter()


@router.get("/checklist", summary="Personalized checklist for a neighbourhood + situation")
async def checklist(
    neighbourhood: str | None = None,
    situation: str | None = None,
    season: str = "current",
) -> dict:
    return not_implemented("firesmart_checklist", target_phase="5")
