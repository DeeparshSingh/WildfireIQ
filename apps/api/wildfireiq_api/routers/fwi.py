"""Fire Weather Index station readings from CWFIS."""

from fastapi import APIRouter

from ._envelope import not_implemented

router = APIRouter()


@router.get("/today", summary="FWI snapshot for stations within bbox")
async def today() -> dict:
    return not_implemented("cwfis_fwi_today", target_phase="1")
