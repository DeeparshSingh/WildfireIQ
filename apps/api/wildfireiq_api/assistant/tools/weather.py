"""Weather and fire-weather tools."""

from __future__ import annotations

from typing import Any

from ...ml.risk_infer import cffdrs_class_for, predict_grid
from ...routers import _data
from .. import gazetteer
from ._location import LOCATION_PROPERTIES, resolve_location
from .base import ToolResult, newest_timestamp, round_floats, tool

WEATHER_SOURCE = "Open-Meteo · ECCC GEM-HRDPS"


@tool(
    name="get_weather",
    description=(
        "Weather for Kamloops: current conditions, the hourly forecast, or the "
        "daily outlook. Temperature, humidity, wind, gusts, precipitation and "
        "vapour-pressure deficit — the last being the drying power of the air, "
        "which drives fire behaviour more than temperature alone."
    ),
    parameters={
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["current", "hourly", "daily"],
                "description": "Default 'current'.",
            },
            "hours": {
                "type": "integer",
                "description": "For kind='hourly': hours ahead, max 72. Default 24.",
            },
            "days": {
                "type": "integer",
                "description": "For kind='daily': days, max 10. Default 5.",
            },
        },
    },
    ttl_s=600,
    tags=("weather",),
)
def get_weather(kind: str = "current", hours: int = 24, days: int = 5) -> ToolResult:
    if kind == "hourly":
        hours = max(1, min(int(hours), 72))
        rows = _data.weather_forecast(hours=hours)
        return ToolResult(
            data={
                "location": "Kamloops",
                "hourly": [
                    {
                        "time_local": str(r.get("ts_local") or ""),
                        "temp_c": round_floats(r.get("temp_c"), 1),
                        "rh_pct": round_floats(r.get("rh_pct"), 0),
                        "wind_kmh": round_floats(r.get("wind_kmh"), 0),
                        "gust_kmh": round_floats(r.get("wind_gust_kmh"), 0),
                        "precip_mm": round_floats(r.get("precip_mm"), 1),
                        "vpd_kpa": round_floats(r.get("vpd_kpa"), 2),
                    }
                    for r in rows
                ],
            },
            source=WEATHER_SOURCE,
            as_of=str(rows[0].get("ts_utc")) if rows else None,
        )

    if kind == "daily":
        days = max(1, min(int(days), 10))
        rows = _data.weather_daily(days=days)
        return ToolResult(
            data={
                "location": "Kamloops",
                "daily": [
                    {
                        "day": str(r.get("day_local") or "")[:10],
                        "forecast": bool(r.get("is_forecast")),
                        "temp_max_c": round_floats(r.get("temp_max_c"), 1),
                        "temp_min_c": round_floats(r.get("temp_min_c"), 1),
                        "rh_min_pct": round_floats(r.get("rh_min_pct"), 0),
                        "precip_mm": round_floats(r.get("precip_mm"), 1),
                        "wind_max_kmh": round_floats(r.get("wind_max_kmh"), 0),
                        "gust_max_kmh": round_floats(r.get("wind_gust_max_kmh"), 0),
                    }
                    for r in rows
                ],
            },
            source=WEATHER_SOURCE,
            as_of=str(rows[-1].get("day_local"))[:10] if rows else None,
        )

    snapshot = _data.weather_current()
    if snapshot is None:
        raise RuntimeError("no current weather snapshot on disk")
    return ToolResult(
        data={
            "location": "Kamloops",
            "temp_c": round_floats(snapshot.get("temp_c"), 1),
            "rh_pct": round_floats(snapshot.get("rh_pct"), 0),
            "wind_kmh": round_floats(snapshot.get("wind_kmh"), 0),
            "wind_dir_deg": round_floats(snapshot.get("wind_dir_deg"), 0),
            "gust_kmh": round_floats(snapshot.get("wind_gust_kmh"), 0),
            "precip_mm": round_floats(snapshot.get("precip_mm"), 1),
            "vpd_kpa": round_floats(snapshot.get("vpd_kpa"), 2),
            "observed_local": str(snapshot.get("observed_at_local") or ""),
        },
        source=WEATHER_SOURCE,
        as_of=str(snapshot.get("fetched_at_utc") or ""),
    )


@tool(
    name="get_fire_weather_index",
    description=(
        "Canadian Fire Weather Index for the modelled regions and, when "
        "available, nearby weather stations. Returns the FWI itself, its "
        "component codes (FFMC, DMC, DC, ISI, BUI) and the CFFDRS fire-danger "
        "class. Use for 'what's the fire danger rating', 'how dry is the "
        "forest', or when explaining why risk is high. These values are "
        "computed by this project from Van Wagner's equations over Open-Meteo "
        "weather — do not attribute them to NRCan or CWFIS."
    ),
    parameters={
        "type": "object",
        "properties": {
            **LOCATION_PROPERTIES,
            "include_stations": {
                "type": "boolean",
                "description": "Include nearby station readings. Default true.",
            },
        },
    },
    ttl_s=900,
    tags=("weather", "risk"),
)
def get_fire_weather_index(
    place: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    include_stations: bool = True,
) -> ToolResult:
    payload: dict[str, Any] = {}
    as_of: str | None = None

    # The project derives FWI from each region's own weather with the Van
    # Wagner equations, so this path does not depend on CWFIS being reachable.
    grid = predict_grid()
    if grid is not None:
        payload["modelled_regions"] = [
            {
                "region": r["key"],
                "label": r["label"],
                "fwi": round_floats(r["fwi_today"], 1),
                "danger_class": r["cffdrs_class"],
            }
            for r in grid["regions"]
        ]
        as_of = grid["observation_day"]

    if include_stations:
        stations = _data.fwi_today()
        if stations:
            location = resolve_location(place, lat, lon)
            scored: list[dict[str, Any]] = []
            for row in stations:
                slat, slon = row.get("latitude"), row.get("longitude")
                if slat is None or slon is None:
                    continue
                scored.append(
                    {
                        "station": row.get("station_name"),
                        "km_away": round(
                            gazetteer.haversine_km(
                                location.lat, location.lon, float(slat), float(slon)
                            ),
                            1,
                        ),
                        "fwi": round_floats(row.get("fwi"), 1),
                        "danger_class": cffdrs_class_for(row.get("fwi")),
                        "ffmc": round_floats(row.get("ffmc"), 1),
                        "dmc": round_floats(row.get("dmc"), 1),
                        "dc": round_floats(row.get("dc"), 1),
                        "isi": round_floats(row.get("isi"), 1),
                        "bui": round_floats(row.get("bui"), 1),
                        "observed": str(row.get("observation_date_local") or "")[:10],
                    }
                )
            scored.sort(key=lambda r: r["km_away"])
            payload["nearest_stations"] = scored[:6]
            payload["location"] = location.as_dict()
            as_of = as_of or newest_timestamp(stations, "fetched_at_utc")
        else:
            payload["stations_note"] = (
                "No CWFIS station readings cached yet. The modelled regional "
                "FWI above is computed independently from Van Wagner's "
                "equations and is what the risk model actually uses."
            )

    if not payload:
        raise RuntimeError("neither modelled nor station fire-weather data is available")

    # Must match ml.risk_infer.cffdrs_class_for, which is what labels the map.
    payload["scale"] = (
        "CFFDRS fire-danger classes by FWI: Low 0-1, Moderate 2-4, High 5-12, "
        "Very High 13-20, Extreme 21 and above"
    )
    return ToolResult(
        data=payload,
        source="WildfireIQ Van Wagner FWI implementation over Open-Meteo daily weather",
        as_of=as_of,
    )


@tool(
    name="get_season_context",
    description=(
        "Where we are in the fire season: days since the last meaningful rain "
        "in Kamloops, and the historical peak date of the Thompson-Okanagan "
        "season. Good framing for 'is it a bad year', 'when does it usually "
        "peak', 'how long has it been dry'."
    ),
    parameters={"type": "object", "properties": {}},
    ttl_s=3600,
    tags=("weather", "climate"),
)
def get_season_context() -> ToolResult:
    context = _data.season_context()
    months = (
        "January February March April May June July August September October November December"
    ).split()
    peak_month = int(context.get("peak_month") or 7)
    return ToolResult(
        data={
            "days_since_5mm_rain": context.get("days_since_5mm_rain"),
            "historical_peak_date": f"{months[peak_month - 1]} {int(context.get('peak_day') or 20)}",
            "peak_basis": context.get("peak_basis"),
        },
        source="Open-Meteo daily weather · BC Wildfire Service historical incidents",
    )
