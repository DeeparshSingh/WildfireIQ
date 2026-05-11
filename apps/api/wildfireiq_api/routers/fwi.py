"""Fire Weather Index station readings from CWFIS."""

from typing import Any

from fastapi import APIRouter

from . import _data
from ._envelope import Envelope, Meta

router = APIRouter()


@router.get("/today", summary="FWI snapshot for stations within bbox")
async def today() -> dict[str, Any]:
    rows = _data.fwi_today()
    return Envelope[list](
        data=rows,
        meta=Meta(
            source="cwfis_fwi_daily",
            attribution="Natural Resources Canada · CWFIS (Canadian Wildland Fire Information System)",
            phase="1",
            note=None if rows else "CWFIS upstream may be transiently unavailable — re-run ingest",
        ),
    ).model_dump(mode="json")
