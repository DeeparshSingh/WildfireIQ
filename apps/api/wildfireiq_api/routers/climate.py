"""Historical climate + CMIP6 projections (Phase 6)."""

from fastapi import APIRouter

from ._envelope import not_implemented

router = APIRouter()


@router.get("/seasonal", summary="Annual fire-season metrics over time")
async def seasonal(metric: str = "area_burned") -> dict:
    return not_implemented("climate_seasonal", target_phase="6")


@router.get("/projection", summary="Climate projection for a SSP scenario + variable")
async def projection(ssp: str = "245", var: str = "tasmax") -> dict:
    return not_implemented("climate_projection", target_phase="6")
