"""Tools for the live wildfire situation: risk, incidents, hotspots, evacuations."""

from __future__ import annotations

from collections import Counter
from typing import Any

from ...ml.risk_infer import predict_grid
from ...routers import _data
from .. import gazetteer
from ._location import LOCATION_HINT, LOCATION_PROPERTIES, resolve_location
from .base import ToolArgumentError, ToolResult, newest_timestamp, round_floats, tool

RISK_SOURCE = "WildfireIQ wildfire_risk_v1 — LightGBM on BC Wildfire Service 1999-2021 + ERA5"
FIRE_SOURCE = "BC Wildfire Service · DataBC (Open Government Licence – British Columbia)"
EVAC_SOURCE = "BC Emergency Management and Climate Readiness (EMCR)"


# ─── AI risk model ───────────────────────────────────────────────────


@tool(
    name="get_wildfire_risk",
    description=(
        "Today's AI wildfire-risk assessment. With no location, returns every "
        "modelled region so they can be compared. With a location, returns the "
        "risk for the H3 hexagon containing it, plus its region's summary. "
        "The model predicts the probability that at least one fire ignites in "
        "the region today, weighted per cell by historical fire density. "
        "Use this for 'how risky is it', 'what's the fire danger', "
        "'compare Kelowna and Kamloops'."
    ),
    parameters={
        "type": "object",
        "properties": {
            **LOCATION_PROPERTIES,
            "region": {
                "type": "string",
                "description": (
                    "Restrict to one modelled region by key: thompson_okanagan, "
                    "central_okanagan, lower_mainland, prince_george."
                ),
            },
        },
    },
    ttl_s=600,
    tags=("risk",),
)
def get_wildfire_risk(
    place: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    region: str | None = None,
) -> ToolResult:
    grid = predict_grid()
    if grid is None:
        raise RuntimeError(
            "The risk model has not been trained on this deployment "
            "(data/models/wildfire_risk_v1 is missing)."
        )

    regions = grid["regions"]
    if region:
        regions = [r for r in regions if r["key"] == region]
        if not regions:
            known = ", ".join(r["key"] for r in grid["regions"])
            raise ToolArgumentError(f"unknown region {region!r}. Known regions: {known}")

    summaries = [
        {
            "region": r["key"],
            "label": r["label"],
            "risk_level": r["risk_level"],
            "probability_of_a_fire_day": round(r["p_region"], 3),
            "fire_weather_index": round_floats(r["fwi_today"], 1),
            "fire_weather_class": r["cffdrs_class"],
            "cells": r["n_cells"],
        }
        for r in regions
    ]

    observation_day = str(grid["observation_day"])[:10]
    payload: dict[str, Any] = {
        "observation_day": observation_day,
        "regions": summaries,
        "scale": "Low < 0.05 ≤ Moderate < 0.20 ≤ High < 0.50 ≤ Extreme (per-cell probability)",
    }

    # Without a location the question is comparative, so add the shape of
    # the map: how many hexagons sit in each class.
    if place is None and lat is None and lon is None:
        cells = [c for c in grid["cells"] if not region or c["region"] == region]
        payload["cell_class_counts"] = dict(Counter(c["risk_class"] for c in cells))
    else:
        location = resolve_location(place, lat, lon)
        cell = _nearest_cell(grid["cells"], location.lat, location.lon)
        if cell is None:
            raise RuntimeError("the risk grid returned no cells")
        distance_km = gazetteer.haversine_km(
            location.lat, location.lon, cell["centroid_lat"], cell["centroid_lon"]
        )
        payload["location"] = location.as_dict()
        payload["cell"] = {
            "h3_cell": cell["h3_cell"],
            "region": cell["region"],
            "region_label": cell["region_label"],
            "risk_class": cell["risk_class"],
            "cell_probability": round(cell["p_cell"], 4),
            "region_probability": round(cell["p_region"], 3),
            "historical_fires_in_this_cell": cell["hist_fire_count"],
            "km_from_requested_point": round(distance_km, 1),
        }
        if distance_km > 60:
            payload["coverage_warning"] = (
                f"{location.label} is {distance_km:.0f} km from the nearest modelled "
                "hexagon. The model covers four regions only "
                "(Thompson-Okanagan, Central Okanagan, Lower Mainland, Prince George); "
                "treat this as out of coverage rather than a real reading."
            )

    return ToolResult(
        data=payload,
        source=RISK_SOURCE,
        as_of=observation_day,
        note=(
            "Informational only. Not for operational firefighting or evacuation "
            "decisions — defer to the BC Wildfire Service."
        ),
    )


def _where_clause(
    origin: Any, lat: float, lon: float, *, always_name_town: bool = False
) -> dict[str, Any]:
    """Say where a point is, in words the model can copy rather than derive.

    Given only latitude and longitude a language model will still narrate a
    direction and a nearby town, and it will get them wrong — the first live
    run placed a fire 77 km east-southeast of Kamloops "southwest near
    Falkland", when it was in fact 11 km from Vernon. Both facts are cheap
    to compute here and impossible to compute reliably in prose.
    """
    out: dict[str, Any] = {}
    if origin is not None:
        out["direction"] = gazetteer.direction_from(origin.lat, origin.lon, lat, lon)
    if origin is not None or always_name_town:
        near = gazetteer.nearest_place(lat, lon)
        if near is not None:
            out["nearest_town"] = (
                f"{near.name}, {gazetteer.haversine_km(lat, lon, near.lat, near.lon):.0f} km"
            )
    return out


def _nearest_cell(cells: list[dict[str, Any]], lat: float, lon: float) -> dict[str, Any] | None:
    if not cells:
        return None
    return min(
        cells,
        key=lambda c: gazetteer.haversine_km(lat, lon, c["centroid_lat"], c["centroid_lon"]),
    )


# ─── Active incidents ────────────────────────────────────────────────


@tool(
    name="get_active_fires",
    description=(
        "Active wildfire incidents reported by the BC Wildfire Service, "
        "optionally within a radius of a place. Returns a count summary plus "
        "the largest or closest incidents. Use for 'are there fires near me', "
        "'how many fires are burning', 'what's the biggest fire right now'."
    ),
    parameters={
        "type": "object",
        "properties": {
            **LOCATION_PROPERTIES,
            "within_km": {
                "type": "number",
                "description": "Radius around the location.",
            },
            "min_hectares": {"type": "number", "description": "Minimum size."},
            "sort_by": {
                "type": "string",
                "enum": ["distance", "size", "newest"],
                "description": "Default: distance with a location, else size.",
            },
            "limit": {"type": "integer", "description": "Incidents to return, max 25."},
        },
    },
    ttl_s=120,
    tags=("fires",),
)
def get_active_fires(
    place: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    within_km: float | None = None,
    min_hectares: float | None = None,
    sort_by: str | None = None,
    limit: int = 8,
) -> ToolResult:
    rows = _data.fires_current()
    if not rows:
        return ToolResult(
            data={"total_active": 0, "incidents": []},
            source=FIRE_SOURCE,
            note="No active-fire snapshot on disk yet.",
        )

    has_location = place is not None or (lat is not None and lon is not None)
    location = resolve_location(place, lat, lon) if has_location else None

    candidates: list[dict[str, Any]] = []
    for row in rows:
        flat, flon = row.get("latitude"), row.get("longitude")
        if flat is None or flon is None:
            continue
        if min_hectares is not None and (row.get("hectares") or 0) < min_hectares:
            continue
        distance = (
            gazetteer.haversine_km(location.lat, location.lon, float(flat), float(flon))
            if location
            else None
        )
        if location and within_km is not None and distance is not None and distance > within_km:
            continue
        candidates.append({**row, "_distance_km": distance})

    order = sort_by or ("distance" if location else "size")
    if order == "distance" and location:
        candidates.sort(key=lambda r: r["_distance_km"] if r["_distance_km"] is not None else 1e9)
    elif order == "newest":
        candidates.sort(key=lambda r: str(r.get("discovery_date_utc") or ""), reverse=True)
    else:
        candidates.sort(key=lambda r: float(r.get("hectares") or 0), reverse=True)

    limit = max(1, min(int(limit), 25))
    incidents = [
        {
            "name": row.get("fire_name") or row.get("fire_id"),
            "fire_id": row.get("fire_id"),
            "hectares": round_floats(row.get("hectares"), 1),
            "stage_of_control": row.get("stage_of_control"),
            "status": row.get("status"),
            "discovered": (str(row.get("discovery_date_utc") or "") or None),
            "lat": round_floats(row.get("latitude"), 4),
            "lon": round_floats(row.get("longitude"), 4),
            **_where_clause(location, float(row["latitude"]), float(row["longitude"])),
            **(
                {"km_away": round(row["_distance_km"], 1)}
                if row.get("_distance_km") is not None
                else {}
            ),
        }
        for row in candidates[:limit]
    ]

    stages = Counter(str(r.get("stage_of_control") or "Unknown") for r in candidates)
    payload: dict[str, Any] = {
        "matched": len(candidates),
        "total_active_in_bc": len(rows),
        "by_stage_of_control": dict(stages),
        "total_hectares_matched": round(sum(float(r.get("hectares") or 0) for r in candidates), 1),
        "incidents": incidents,
    }
    if location:
        payload["location"] = location.as_dict()
        payload["search_radius_km"] = within_km

    return ToolResult(
        data=payload,
        source=FIRE_SOURCE,
        as_of=newest_timestamp(rows, "fetched_at_utc"),
    )


@tool(
    name="get_satellite_hotspots",
    description=(
        "NASA FIRMS satellite thermal detections (VIIRS/MODIS) from the last N "
        "hours. These are heat signatures, not confirmed fires — they can be "
        "flares, hot industrial sites, or a fire already reported. Use when the "
        "user asks about satellite detections, or wants the earliest signal of "
        "something not yet in the official incident list."
    ),
    parameters={
        "type": "object",
        "properties": {
            **LOCATION_PROPERTIES,
            "hours": {"type": "integer", "description": "Look-back, 1-168. Default 24."},
            "within_km": {"type": "number", "description": "Radius around the location."},
        },
    },
    ttl_s=300,
    tags=("fires",),
)
def get_satellite_hotspots(
    place: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    hours: int = 24,
    within_km: float | None = None,
) -> ToolResult:
    hours = max(1, min(int(hours), 168))
    rows = _data.firms_hotspots(since_hours=hours)
    has_location = place is not None or (lat is not None and lon is not None)
    location = resolve_location(place, lat, lon) if has_location else None

    kept: list[dict[str, Any]] = []
    for row in rows:
        hlat, hlon = row.get("latitude"), row.get("longitude")
        if hlat is None or hlon is None:
            continue
        distance = (
            gazetteer.haversine_km(location.lat, location.lon, float(hlat), float(hlon))
            if location
            else None
        )
        if location and within_km is not None and distance is not None and distance > within_km:
            continue
        kept.append({**row, "_distance_km": distance})

    kept.sort(key=lambda r: float(r.get("frp") or 0), reverse=True)
    payload: dict[str, Any] = {
        "window_hours": hours,
        "detections": len(kept),
        "by_satellite": dict(Counter(str(r.get("source") or "unknown") for r in kept)),
        "strongest": [
            {
                "lat": round_floats(r.get("latitude"), 4),
                "lon": round_floats(r.get("longitude"), 4),
                "detected_utc": str(r.get("acq_datetime_utc") or ""),
                "fire_radiative_power_mw": round_floats(r.get("frp"), 1),
                "confidence": r.get("confidence"),
                **_where_clause(
                    location, float(r["latitude"]), float(r["longitude"]), always_name_town=True
                ),
                **({"km_away": round(r["_distance_km"], 1)} if r.get("_distance_km") else {}),
            }
            for r in kept[:8]
        ],
    }
    if location:
        payload["location"] = location.as_dict()

    return ToolResult(
        data=payload,
        source="NASA FIRMS · VIIRS + MODIS near-real-time",
        as_of=newest_timestamp(rows, "fetched_at_utc"),
        note="Thermal anomalies, not confirmed wildfires.",
    )


# ─── Evacuations ─────────────────────────────────────────────────────


@tool(
    name="check_evacuation_status",
    description=(
        "Whether a specific point falls inside an active evacuation ORDER or "
        "ALERT polygon. This is a point-in-polygon test against the live EMCR "
        "feed. Use whenever the user asks about their own address, "
        "neighbourhood, or 'do I have to leave'."
    ),
    parameters={
        "type": "object",
        "properties": dict(LOCATION_PROPERTIES),
        "description": LOCATION_HINT,
    },
    ttl_s=60,
    tags=("evac", "safety"),
)
def check_evacuation_status(
    place: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> ToolResult:
    from shapely import wkt
    from shapely.geometry import Point

    location = resolve_location(place, lat, lon, required=True)
    rows = _data.evac_active()
    point = Point(location.lon, location.lat)

    matches: list[dict[str, Any]] = []
    for row in rows:
        geom = row.get("geom_wkt")
        if not geom:
            continue
        try:
            polygon = wkt.loads(geom)
        except Exception:
            continue
        if polygon.contains(point):
            matches.append(
                {
                    "event": row.get("event_name") or row.get("order_alert_name"),
                    "status": row.get("status"),
                    "issued_utc": str(row.get("issued_utc") or ""),
                    "issuing_agency": row.get("issuing_agency"),
                }
            )

    statuses = [str(m.get("status") or "").lower() for m in matches]
    if any("order" in s for s in statuses):
        status = "order"
    elif any("alert" in s for s in statuses):
        status = "alert"
    else:
        status = "clear"

    return ToolResult(
        data={
            "location": location.as_dict(),
            "status": status,
            "meaning": {
                "order": "Evacuation ORDER — leave immediately, this is not optional.",
                "alert": "Evacuation ALERT — be ready to leave on short notice.",
                "clear": "No active evacuation order or alert covers this point.",
            }[status],
            "matches": matches,
            "active_zones_checked": len(rows),
        },
        source=EVAC_SOURCE,
        as_of=newest_timestamp(rows, "fetched_at_utc"),
        note=(
            "Always confirm against emergencyinfobc.gov.bc.ca and the local "
            "regional district before acting."
        ),
    )


@tool(
    name="list_evacuation_orders",
    description=(
        "Every active evacuation order and alert in the feed, newest first. "
        "Use for 'what evacuations are in effect', or to name the events near "
        "a place. For one specific address, use check_evacuation_status instead."
    ),
    parameters={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["order", "alert", "all"],
                "description": "Default 'all'.",
            },
            "include_rescinded": {
                "type": "boolean",
                "description": "Include rescinded zones. Default false.",
            },
            "limit": {"type": "integer", "description": "Max zones, up to 30."},
        },
    },
    ttl_s=60,
    tags=("evac", "safety"),
)
def list_evacuation_orders(
    status: str = "all",
    include_rescinded: bool = False,
    limit: int = 15,
) -> ToolResult:
    rows = _data.evac_active()
    kept: list[dict[str, Any]] = []
    for row in rows:
        state = str(row.get("status") or "").lower()
        if not include_rescinded and "rescind" in state:
            continue
        if status == "order" and "order" not in state:
            continue
        if status == "alert" and "alert" not in state:
            continue
        kept.append(row)

    kept.sort(key=lambda r: str(r.get("issued_utc") or ""), reverse=True)
    limit = max(1, min(int(limit), 30))

    return ToolResult(
        data={
            "active_zones": len(kept),
            "by_status": dict(Counter(str(r.get("status") or "Unknown") for r in kept)),
            "zones": [
                {
                    "event": row.get("event_name") or row.get("order_alert_name"),
                    "status": row.get("status"),
                    "agency": row.get("issuing_agency"),
                    "issued_utc": str(row.get("issued_utc") or ""),
                    "area_hectares": round_floats(row.get("area_hectares"), 0),
                }
                for row in kept[:limit]
            ],
        },
        source=EVAC_SOURCE,
        as_of=newest_timestamp(rows, "fetched_at_utc"),
    )
