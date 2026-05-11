"""Historical climate + CMIP6 projections (Phase 6)."""

from typing import Any

from fastapi import APIRouter

from . import _data
from ._envelope import Envelope, Meta

router = APIRouter()


@router.get("/seasonal", summary="Annual fire-season metrics over time")
async def seasonal(metric: str = "area_burned") -> dict[str, Any]:
    rows = _data.fires_seasonal_summary()
    return Envelope[list](
        data=rows,
        meta=Meta(
            source="databc_fires_historical",
            attribution="BC Wildfire Service · DataBC · historical fire records",
            phase="1",
            note=None if rows else "Run `--only databc_fires_historical` then re-call",
        ),
    ).model_dump(mode="json")


@router.get("/projection", summary="Climate projection for a SSP scenario + variable")
async def projection(ssp: str = "ssp245", var: str = "tasmean") -> dict[str, Any]:
    rows = _data.climate_projections(ssp=ssp, var=var)
    return Envelope[list](
        data=rows,
        meta=Meta(
            source="climatedata_projections",
            attribution="Synthetic placeholder · Phase 6 replaces with CMIP6 from ClimateData.ca",
            phase="1",
            note="Synthetic linear extrapolation. Phase 6 swaps in real CMIP6 ensembles.",
        ),
    ).model_dump(mode="json")
