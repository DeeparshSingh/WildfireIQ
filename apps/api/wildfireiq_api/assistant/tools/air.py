"""Air quality tools: current AQHI, the PM2.5 forecast, health guidance, smoke history."""

from __future__ import annotations

import json
from typing import Any

from ...ml.aq_infer import predict_calendar, predict_forecast
from ...paths import GEO_ROOT
from ...routers import _data
from .. import gazetteer
from ._location import LOCATION_PROPERTIES, resolve_location
from .base import ToolResult, newest_timestamp, round_floats, tool

AQ_SOURCE = "ECCC GeoMet AQHI + WAQI/AQICN"
FORECAST_SOURCE = "WildfireIQ aq_forecaster_v1 — LightGBM quantile on Open-Meteo CAMS + weather"


def _aqhi_band(aqhi: float | None) -> str:
    """Health Canada's four bands. 10+ is reported as '10+', not 11."""
    if aqhi is None:
        return "Unknown"
    if aqhi <= 3:
        return "Low Risk"
    if aqhi <= 6:
        return "Moderate Risk"
    if aqhi <= 10:
        return "High Risk"
    return "Very High Risk"


@tool(
    name="get_air_quality",
    description=(
        "Current air quality: the Air Quality Health Index at nearby monitoring "
        "stations plus the pollutant breakdown (PM2.5, PM10, O3, NO2, SO2, CO). "
        "Use for 'is the air bad', 'what's the AQHI', 'how smoky is it'."
    ),
    parameters={
        "type": "object",
        "properties": {
            **LOCATION_PROPERTIES,
            "within_km": {
                "type": "number",
                "description": "Only report stations within this radius. Default 150.",
            },
        },
    },
    ttl_s=180,
    tags=("air",),
)
def get_air_quality(
    place: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    within_km: float = 150.0,
) -> ToolResult:
    location = resolve_location(place, lat, lon)
    stations = _data.aqhi_current()
    pollutants = _data.aq_pollutants_latest()

    nearby: list[dict[str, Any]] = []
    for row in stations:
        slat, slon = row.get("latitude"), row.get("longitude")
        if slat is None or slon is None:
            continue
        distance = gazetteer.haversine_km(location.lat, location.lon, float(slat), float(slon))
        if distance > within_km:
            continue
        aqhi = row.get("aqhi")
        nearby.append(
            {
                "station": row.get("station_name"),
                "aqhi": round_floats(aqhi, 1),
                "band": _aqhi_band(float(aqhi)) if aqhi is not None else "Unknown",
                "km_away": round(distance, 1),
                "observed_utc": str(row.get("observation_datetime_utc") or ""),
            }
        )
    nearby.sort(key=lambda r: r["km_away"])

    closest = nearby[0] if nearby else None
    payload: dict[str, Any] = {
        "location": location.as_dict(),
        "nearest_station": closest,
        "stations": nearby[:6],
        "stations_within_radius": len(nearby),
    }
    if pollutants:
        payload["pollutants"] = {
            "station": pollutants.get("station_name"),
            "pm2_5_ug_m3": round_floats(pollutants.get("pm25"), 1),
            "pm10_ug_m3": round_floats(pollutants.get("pm10"), 1),
            "ozone": round_floats(pollutants.get("o3"), 1),
            "no2": round_floats(pollutants.get("no2"), 1),
            "so2": round_floats(pollutants.get("so2"), 1),
            "co": round_floats(pollutants.get("co"), 1),
            "dominant_pollutant": pollutants.get("dominant_pollutant"),
            "observed_utc": str(pollutants.get("observation_time_utc") or ""),
        }
    if not nearby:
        payload["note"] = (
            f"No AQHI station within {within_km:.0f} km of {location.label}. "
            "BC's AQHI network is sparse outside the larger centres."
        )

    return ToolResult(
        data=payload,
        source=AQ_SOURCE,
        as_of=newest_timestamp(stations, "observation_datetime_utc", "fetched_at_utc"),
    )


@tool(
    name="get_air_quality_forecast",
    description=(
        "48-hour PM2.5 forecast for Kamloops with q10/q50/q90 uncertainty bands "
        "and the AQHI each level implies, from the project's own trained "
        "quantile model. Use for 'will the smoke clear', 'is tomorrow better', "
        "'when can I go for a run'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "hours": {
                "type": "integer",
                "description": "Horizon to report, up to 48. Default 48.",
            }
        },
    },
    ttl_s=900,
    tags=("air",),
)
def get_air_quality_forecast(hours: int = 48) -> ToolResult:
    payload = predict_forecast()
    if payload is None:
        raise RuntimeError("The air-quality forecaster is not trained on this deployment.")

    hours = max(1, min(int(hours), 48))
    points = [p for p in payload["forecasts"] if p["horizon_h"] <= hours]
    observations = payload.get("observations") or []

    worst = max(points, key=lambda p: p["q50"]) if points else None
    best = min(points, key=lambda p: p["q50"]) if points else None

    return ToolResult(
        data={
            "issued_utc": payload["issued_at_utc"],
            "recent_observed_pm2_5": round_floats(
                observations[-1]["pm2_5"] if observations else None, 1
            ),
            "forecast": [
                {
                    "hours_ahead": p["horizon_h"],
                    "time_utc": p["time_utc"],
                    "pm2_5_median": round(p["q50"], 1),
                    "pm2_5_range_q10_q90": [round(p["q10"], 1), round(p["q90"], 1)],
                    "aqhi": round(p["aqhi_q50"], 1),
                    "band": _aqhi_band(p["aqhi_q50"]),
                }
                for p in points
            ],
            "peak": (
                {
                    "hours_ahead": worst["horizon_h"],
                    "pm2_5_median": round(worst["q50"], 1),
                    "band": _aqhi_band(worst["aqhi_q50"]),
                }
                if worst
                else None
            ),
            "cleanest": (
                {"hours_ahead": best["horizon_h"], "pm2_5_median": round(best["q50"], 1)}
                if best
                else None
            ),
        },
        source=FORECAST_SOURCE,
        as_of=payload["issued_at_utc"],
        note="Kamloops only. The q10-q90 band is the model's own uncertainty, not a scenario range.",
    )


@tool(
    name="get_health_guidance",
    description=(
        "Health Canada AQHI guidance for a given index value, for the general "
        "population, at-risk people (asthma, heart or lung conditions, "
        "children, seniors, pregnancy), or outdoor workers. Call this whenever "
        "the user asks what they should DO about smoke or air quality — never "
        "improvise health advice."
    ),
    parameters={
        "type": "object",
        "properties": {
            "aqhi": {
                "type": "number",
                "description": "AQHI value to look up. Omit to return every band.",
            },
            "audience": {
                "type": "string",
                "enum": ["general", "at_risk", "outdoor_workers", "all"],
                "description": "Which advice line to return. Default 'all'.",
            },
        },
    },
    ttl_s=3600,
    tags=("air", "health"),
)
def get_health_guidance(aqhi: float | None = None, audience: str = "all") -> ToolResult:
    path = GEO_ROOT / "health_guidance.json"
    if not path.exists():
        raise RuntimeError("health guidance reference file is missing")
    guidance = json.loads(path.read_text())

    bands = guidance["bands"]
    if aqhi is not None:
        value = float(aqhi)
        bands = [b for b in bands if b["aqhi_min"] <= value <= b["aqhi_max"]] or bands[-1:]

    keys = ["general", "at_risk", "outdoor_workers"] if audience == "all" else [audience]
    return ToolResult(
        data={
            "queried_aqhi": aqhi,
            "bands": [
                {
                    "range": f"{b['aqhi_min']}-{b['aqhi_max']}",
                    "label": b["label"],
                    **{k: b[k] for k in keys if k in b},
                }
                for b in bands
            ],
            "links": guidance.get("links", []),
        },
        source=guidance.get("source", "Health Canada AQHI"),
        note="General public-health guidance, not personal medical advice.",
    )


@tool(
    name="get_smoke_history",
    description=(
        "Daily peak and mean PM2.5 for Kamloops over the last N days — the "
        "smoke-event calendar. Use for 'how bad has this summer been', 'when "
        "was the last clean-air week', 'how many smoky days so far'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "days": {"type": "integer", "description": "Look-back window, 7-120. Default 60."},
            "smoky_threshold_pm25": {
                "type": "number",
                "description": "PM2.5 above which a day counts as smoky. Default 35 µg/m³ (Canada's 24-hour objective).",
            },
        },
    },
    ttl_s=1800,
    tags=("air",),
)
def get_smoke_history(days: int = 60, smoky_threshold_pm25: float = 35.0) -> ToolResult:
    days = max(7, min(int(days), 120))
    payload = predict_calendar(days=days)
    if payload is None:
        raise RuntimeError("the hourly air-quality archive is not available")

    rows = payload["days"]
    smoky = [r for r in rows if float(r.get("max_pm25") or 0) >= smoky_threshold_pm25]
    worst = max(rows, key=lambda r: float(r.get("max_pm25") or 0)) if rows else None

    return ToolResult(
        data={
            "window_days": len(rows),
            "smoky_days": len(smoky),
            "smoky_threshold_pm25": smoky_threshold_pm25,
            "worst_day": (
                {
                    "date": worst["day_utc"],
                    "peak_pm2_5": round(float(worst["max_pm25"]), 1),
                    "peak_aqhi": round(float(worst["max_aqhi"]), 1),
                }
                if worst
                else None
            ),
            "mean_of_daily_peaks_pm2_5": (
                round(sum(float(r["max_pm25"]) for r in rows) / len(rows), 1) if rows else None
            ),
            "recent_days": [
                {
                    "date": r["day_utc"],
                    "peak_pm2_5": round(float(r["max_pm25"]), 1),
                    "peak_aqhi": round(float(r["max_aqhi"]), 1),
                }
                for r in rows[-14:]
            ],
        },
        source="Open-Meteo CAMS air-quality reanalysis · daily aggregation",
        as_of=rows[-1]["day_utc"] if rows else None,
    )


@tool(
    name="get_smoke_plume_forecast",
    description=(
        "ECCC FireWork wildfire-smoke plume forecast timesteps with the "
        "predicted PM2.5 at Kamloops for each hour. Use when the user asks "
        "where the smoke is coming from or when a plume arrives."
    ),
    parameters={"type": "object", "properties": {}},
    ttl_s=1800,
    tags=("air",),
)
def get_smoke_plume_forecast() -> ToolResult:
    rows = _data.smoke_forecast_metadata()
    if not rows:
        raise RuntimeError("no FireWork smoke forecast timesteps are cached")
    return ToolResult(
        data={
            "timesteps": len(rows),
            "first_valid_utc": str(rows[0].get("valid_time_utc") or ""),
            "last_valid_utc": str(rows[-1].get("valid_time_utc") or ""),
            "hourly": [
                {
                    "valid_utc": str(r.get("valid_time_utc") or ""),
                    "pm2_5_at_kamloops": round_floats(r.get("pm25_at_kamloops"), 1),
                }
                for r in rows[:36]
            ],
        },
        source="ECCC RAQDPS-FW (FireWork) via MSC GeoMet",
        as_of=newest_timestamp(rows, "fetched_at_utc"),
        note="The plume imagery itself renders on the map's Smoke layer.",
    )
