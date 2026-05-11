"""Active evacuation orders and alerts from BC Emergency Management."""

from typing import Any

from fastapi import APIRouter
from shapely import wkt
from shapely.geometry import Point

from . import _data
from ._envelope import Envelope, Meta

router = APIRouter()


@router.get("/active", summary="All active evacuation orders + alerts in bbox")
async def active() -> dict[str, Any]:
    rows = _data.evac_active()
    return Envelope[list](
        data=rows,
        meta=Meta(
            source="bcem_evac",
            attribution="BC Emergency Management Climate Readiness (EMCR)",
            phase="1",
        ),
    ).model_dump(mode="json")


@router.get("/check", summary="Check evacuation status at a coordinate")
async def check(lat: float, lon: float) -> dict[str, Any]:
    rows = _data.evac_active()
    pt = Point(lon, lat)
    matched: list[dict[str, Any]] = []
    for r in rows:
        geom_wkt = r.get("geom_wkt")
        if not geom_wkt:
            continue
        try:
            poly = wkt.loads(geom_wkt)
        except Exception:
            continue
        if poly.contains(pt):
            matched.append(r)

    status = "clear"
    if matched:
        statuses = [str(m.get("status", "")).lower() for m in matched]
        if any("order" in s for s in statuses):
            status = "order"
        elif any("alert" in s for s in statuses):
            status = "alert"

    return Envelope[dict](
        data={"status": status, "matches": matched, "queried": {"lat": lat, "lon": lon}},
        meta=Meta(
            source="bcem_evac",
            attribution="BC Emergency Management Climate Readiness (EMCR)",
            phase="1",
        ),
    ).model_dump(mode="json")
