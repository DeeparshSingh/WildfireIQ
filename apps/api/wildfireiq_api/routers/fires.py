"""Active + historical fire incidents and FIRMS hotspots."""

from typing import Any

from fastapi import APIRouter

from . import _data
from ._envelope import Envelope, Meta

router = APIRouter()


@router.get("/current", summary="Current active BC fires within bbox")
async def current() -> dict[str, Any]:
    rows = _data.fires_current()
    return Envelope[list](
        data=rows,
        meta=Meta(
            source="databc_fires_current",
            attribution="BC Wildfire Service · DataBC · Open Government Licence – British Columbia",
            phase="1",
            note=None if rows else "No fires_current.parquet yet — run `uv run python scripts/ingest/bootstrap.py --only databc_fires_current`",
        ),
    ).model_dump(mode="json")


@router.get("/hotspots", summary="NASA FIRMS satellite hotspots (last N hours)")
async def hotspots(since: str = "24h") -> dict[str, Any]:
    hours = 24
    if since.endswith("h") and since[:-1].isdigit():
        hours = int(since[:-1])
    rows = _data.firms_hotspots(since_hours=hours)
    return Envelope[list](
        data=rows,
        meta=Meta(
            source="firms_hotspots",
            attribution="NASA FIRMS · VIIRS + MODIS Near-Real-Time fire data",
            phase="1",
            note=None if rows else "No firms_hotspots_recent.parquet yet — needs FIRMS_MAP_KEY in .env then re-run ingest",
        ),
    ).model_dump(mode="json")


@router.get("/historical", summary="Historical BC fires for a given year")
async def historical(year: int | None = None) -> dict[str, Any]:
    rows = _data.fires_historical(year=year)
    return Envelope[list](
        data=rows,
        meta=Meta(
            source="databc_fires_historical",
            attribution="BC Wildfire Service · DataBC · 1999–today",
            phase="1",
            note=None if rows else "Run bootstrap to ingest historical fires",
        ),
    ).model_dump(mode="json")
