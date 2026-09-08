"""Fire Weather Index at representative BC weather stations.

These values are computed here, by `ml/fwi.py`, from Open-Meteo weather run
through Van Wagner's equations — they are not NRCan's published readings. The
route used to be attributed to CWFIS, which credited NRCan for our arithmetic.
NRCan's own figures are ingested separately as a cross-check; see
`ingest/cwfis_fwi.py` and the data dictionary.
"""

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
            source="derived_fwi_stations",
            attribution=(
                "Fire Weather Index computed by WildfireIQ from Van Wagner & Pickett "
                "(1985), over Open-Meteo daily weather"
            ),
            note=None if rows else "no station rows cached yet — re-run ingest",
        ),
    ).model_dump(mode="json")
