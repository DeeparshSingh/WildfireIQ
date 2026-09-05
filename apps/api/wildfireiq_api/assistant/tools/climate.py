"""Historical and long-term tools: season records, trends, the fire archive."""

from __future__ import annotations

import math
from typing import Any

from ...routers import _data
from ...routers import climate as climate_router
from .. import gazetteer
from ._location import LOCATION_PROPERTIES, resolve_location
from .base import ToolResult, round_floats, tool

FIRE_ARCHIVE_SOURCE = "BC Wildfire Service historical incidents 1999-present · DataBC"
SEASONAL_SOURCE = "BC Wildfire Service · Open-Meteo ERA5 · WildfireIQ Van Wagner FWI"

#: Metrics the seasonal table carries, with the plain-language names the
#: model should use when it reports them.
_METRIC_LABELS: dict[str, str] = {
    "area_burned_ha": "area burned (hectares)",
    "fire_count": "number of fires",
    "largest_fire_ha": "largest single fire (hectares)",
    "season_start_doy": "first fire day of year",
    "season_end_doy": "last fire day of year",
    "season_length_days": "fire-season length (days)",
    "mean_jul_temp_c": "mean July temperature (°C)",
    "julaug_precip_mm": "July-August precipitation (mm)",
    "mean_julaug_vpd_kpa": "mean July-August vapour-pressure deficit (kPa)",
    "max_julaug_fwi": "peak July-August Fire Weather Index",
    "days_fwi_ge_19": "days with FWI at or above 19",
}


@tool(
    name="get_seasonal_history",
    description=(
        "Per-year Thompson-Okanagan fire-season record from 1999: area burned, "
        "fire count, season start/end/length, July temperature, summer rainfall, "
        "vapour-pressure deficit and peak Fire Weather Index. Use for 'how does "
        "this year compare', 'what was the worst year', 'how much burned in 2023'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "year_from": {"type": "integer", "description": "First year to include."},
            "year_to": {"type": "integer", "description": "Last year to include."},
            "metrics": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Subset of columns to return. Options: "
                    + ", ".join(_METRIC_LABELS)
                    + ". Omit for all."
                ),
            },
            "rank_by": {
                "type": "string",
                "description": "Rank years by this metric, worst first.",
            },
            "top_n": {"type": "integer", "description": "Years to return with rank_by. Default 5."},
        },
    },
    ttl_s=3600,
    tags=("climate",),
)
def get_seasonal_history(
    year_from: int | None = None,
    year_to: int | None = None,
    metrics: list[str] | None = None,
    rank_by: str | None = None,
    top_n: int = 5,
) -> ToolResult:
    rows = _data.seasonal_metrics()
    if not rows:
        raise RuntimeError("seasonal metrics have not been built on this deployment")

    if year_from is not None:
        rows = [r for r in rows if int(r["year"]) >= year_from]
    if year_to is not None:
        rows = [r for r in rows if int(r["year"]) <= year_to]
    if not rows:
        raise RuntimeError("no seasons in that year range")

    keep = [m for m in (metrics or list(_METRIC_LABELS)) if m in _METRIC_LABELS]
    if not keep:
        keep = list(_METRIC_LABELS)

    if rank_by:
        if rank_by not in _METRIC_LABELS:
            raise ValueError(f"unknown metric {rank_by!r}; options: {', '.join(_METRIC_LABELS)}")
        ranked = [r for r in rows if r.get(rank_by) is not None]
        ranked.sort(key=lambda r: float(r[rank_by]), reverse=True)
        rows = ranked[: max(1, min(int(top_n), 15))]
        keep = list(dict.fromkeys([rank_by, *keep]))

    latest = max(int(r["year"]) for r in _data.seasonal_metrics())
    return ToolResult(
        data={
            "column_meanings": {k: _METRIC_LABELS[k] for k in keep},
            "seasons": [
                {"year": int(r["year"]), **{k: round_floats(r.get(k), 1) for k in keep}}
                for r in rows
            ],
        },
        source=SEASONAL_SOURCE,
        as_of=str(latest),
        note=(
            f"Complete seasons only, ending {latest}. The season currently under way "
            "is withheld until October so a partial year cannot distort comparisons."
        ),
    )


@tool(
    name="get_climate_trends",
    description=(
        "Theil-Sen trend slopes with bootstrap 95% confidence intervals for the "
        "seasonal metrics — the statistical answer to 'is it getting worse'. A "
        "confidence interval that spans zero means the trend is not "
        "distinguishable from noise, and should be reported that way."
    ),
    parameters={
        "type": "object",
        "properties": {
            "metric": {
                "type": "string",
                "description": "One metric to report. Omit for all. Options: "
                + ", ".join(_METRIC_LABELS),
            }
        },
    },
    ttl_s=3600,
    tags=("climate",),
)
async def get_climate_trends(metric: str | None = None) -> ToolResult:
    # Calling the router keeps the assistant's numbers byte-identical to the
    # Climate page's. Re-deriving Theil-Sen here would be one more place for
    # the bootstrap settings to drift.
    envelope = await climate_router.trends()
    payload = envelope["data"]
    if not payload:
        raise RuntimeError("seasonal metrics have not been built on this deployment")

    entries = payload["metrics"]
    if metric:
        if metric not in entries:
            raise ValueError(f"unknown metric {metric!r}; options: {', '.join(entries)}")
        entries = {metric: entries[metric]}

    out: dict[str, Any] = {}
    for name, stats in entries.items():
        lo, hi = stats["slope_ci_lo"], stats["slope_ci_hi"]
        significant = (lo > 0 and hi > 0) or (lo < 0 and hi < 0)
        out[name] = {
            "meaning": _METRIC_LABELS.get(name, name),
            "change_per_year": round_floats(stats["slope_per_year"], 3),
            "ci_95": [round_floats(lo, 3), round_floats(hi, 3)],
            "change_over_record": round_floats(stats["delta_over_span"], 1),
            "distinguishable_from_noise": significant,
        }

    return ToolResult(
        data={
            "years": [payload["year_min"], payload["year_max"]],
            "method": "Theil-Sen slope, 1000-sample bootstrap 95% CI",
            "trends": out,
        },
        source=SEASONAL_SOURCE,
        as_of=str(payload["year_max"]),
    )


@tool(
    name="get_historical_fires",
    description=(
        "Query the 1999-present BC fire archive: counts, area burned, causes, "
        "and the largest incidents, optionally within a radius of a place or "
        "within a year range. Use for 'has anything burned near here before', "
        "'how many fires were human-caused', 'what was the biggest fire ever "
        "near Kelowna'."
    ),
    parameters={
        "type": "object",
        "properties": {
            **LOCATION_PROPERTIES,
            "within_km": {"type": "number", "description": "Radius around the location."},
            "year_from": {"type": "integer", "description": "Earliest fire year."},
            "year_to": {"type": "integer", "description": "Latest fire year."},
            "min_hectares": {"type": "number", "description": "Minimum size."},
            "limit": {"type": "integer", "description": "Incidents to list, max 15."},
        },
    },
    ttl_s=3600,
    tags=("climate", "fires"),
)
def get_historical_fires(
    place: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    within_km: float | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    min_hectares: float | None = None,
    limit: int = 8,
) -> ToolResult:
    frame = _data.fires_historical_frame()
    if frame is None or frame.empty:
        raise RuntimeError("the historical fire archive has not been ingested")

    df = frame
    if year_from is not None:
        df = df[df["fire_year"] >= year_from]
    if year_to is not None:
        df = df[df["fire_year"] <= year_to]
    if min_hectares is not None:
        df = df[df["hectares"].fillna(0) >= min_hectares]

    has_location = place is not None or (lat is not None and lon is not None)
    location = resolve_location(place, lat, lon) if has_location else None
    if location is not None:
        radius = within_km if within_km is not None else 50.0
        # Bound by a bounding box first: haversine over 96,000 rows is
        # avoidable work when a degree box discards almost all of them.
        dlat = radius / 111.0
        dlon = radius / max(1e-6, 111.0 * abs(math.cos(math.radians(location.lat))))
        df = df[
            df["latitude"].between(location.lat - dlat, location.lat + dlat)
            & df["longitude"].between(location.lon - dlon, location.lon + dlon)
        ]
        keep = [
            gazetteer.haversine_km(location.lat, location.lon, float(a), float(b)) <= radius
            for a, b in zip(df["latitude"], df["longitude"], strict=True)
        ]
        df = df[keep]

    if df.empty:
        return ToolResult(
            data={
                "matched": 0,
                "location": location.as_dict() if location else None,
                "message": "No archived fires match those filters.",
            },
            source=FIRE_ARCHIVE_SOURCE,
        )

    by_cause = (
        df["ignition_cause"].fillna("Unknown").value_counts().head(6).to_dict()
        if "ignition_cause" in df.columns
        else {}
    )
    by_year = df["fire_year"].value_counts().sort_index().tail(10).to_dict()
    largest = df.nlargest(max(1, min(int(limit), 15)), "hectares")

    payload: dict[str, Any] = {
        "matched_fires": len(df),
        "years": [int(df["fire_year"].min()), int(df["fire_year"].max())],
        "total_hectares": round(float(df["hectares"].fillna(0).sum()), 1),
        "by_ignition_cause": {str(k): int(v) for k, v in by_cause.items()},
        "fires_per_year_recent": {str(k): int(v) for k, v in by_year.items()},
        "largest": [
            {
                "name": row.get("fire_name") or row.get("fire_id"),
                "year": int(row["fire_year"]),
                "hectares": round(float(row["hectares"] or 0), 1),
                "cause": row.get("ignition_cause"),
                "discovered": str(row.get("discovery_date_utc") or "")[:10],
                **(
                    {
                        "km_away": round(
                            gazetteer.haversine_km(
                                location.lat,
                                location.lon,
                                float(row["latitude"]),
                                float(row["longitude"]),
                            ),
                            1,
                        ),
                        # Computed here for the same reason as in situation.py:
                        # a model asked to infer a bearing from coordinates
                        # will state one, and it will be wrong.
                        "direction": gazetteer.direction_from(
                            location.lat,
                            location.lon,
                            float(row["latitude"]),
                            float(row["longitude"]),
                        ),
                    }
                    if location is not None
                    else {}
                ),
            }
            for row in largest.to_dict(orient="records")
        ],
    }
    if location is not None:
        payload["location"] = location.as_dict()
        payload["search_radius_km"] = within_km if within_km is not None else 50.0

    return ToolResult(data=payload, source=FIRE_ARCHIVE_SOURCE)


@tool(
    name="get_fire_danger_projection",
    description=(
        "How many days per decade reach FWI 19 or higher under low, medium and "
        "high emissions scenarios. This is a coarse extrapolation — a "
        "regression of observed July temperature onto observed high-danger "
        "days, evaluated at scenario warming — not a physics model run, and it "
        "must be described that way. Use for 'what happens by 2040'."
    ),
    parameters={"type": "object", "properties": {}},
    ttl_s=3600,
    tags=("climate",),
)
async def get_fire_danger_projection() -> ToolResult:
    envelope = await climate_router.fwi_projection()
    payload = envelope["data"]
    if not payload:
        raise RuntimeError("not enough seasonal history to fit the projection")
    return ToolResult(
        data={
            "scenarios": {
                name: [
                    {
                        "decade": row["decade"],
                        "july_temp_c": round(row["july_temp_c"], 1),
                        "days_fwi_ge_19": row["days_fwi_ge_19"],
                        "observed": row["observed"],
                    }
                    for row in rows
                ]
                for name, rows in payload["scenarios"].items()
            },
            "fit": round_floats(payload["fit"], 2),
        },
        source="WildfireIQ derived heuristic",
        note=payload["method"],
    )
