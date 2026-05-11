"""Tiny read layer over the processed Parquet files.

Routers should call into this module rather than reading Parquet directly,
so caching and missing-file handling stay consistent.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

from ..paths import PROCESSED_ROOT


def _read_parquet_safe(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _records(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    # Replace NaN with None so JSON serialisation is clean.
    return [
        {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


# ─── Public read helpers ─────────────────────────────────────────────


def fires_current() -> list[dict[str, Any]]:
    return _records(_read_parquet_safe(PROCESSED_ROOT / "fires_current.parquet"))


def fires_historical(year: int | None = None, limit: int = 5000) -> list[dict[str, Any]]:
    df = _read_parquet_safe(PROCESSED_ROOT / "fires_historical.parquet")
    if df is None:
        return []
    if year is not None and "fire_year" in df.columns:
        df = df[df["fire_year"] == year]
    return _records(df.head(limit))


def firms_hotspots(since_hours: int = 24, limit: int = 10000) -> list[dict[str, Any]]:
    df = _read_parquet_safe(PROCESSED_ROOT / "firms_hotspots_recent.parquet")
    if df is None:
        return []
    if "acq_datetime_utc" in df.columns:
        df = df.copy()
        df["_ts"] = pd.to_datetime(df["acq_datetime_utc"], errors="coerce", utc=True)
        cutoff = pd.Timestamp.utcnow() - pd.Timedelta(hours=since_hours)
        df = df[df["_ts"].notna() & (df["_ts"] >= cutoff)]
        df = df.drop(columns=["_ts"])
    return _records(df.head(limit))


def weather_current() -> dict[str, Any] | None:
    df = _read_parquet_safe(PROCESSED_ROOT / "weather_kamloops_current.parquet")
    if df is None or df.empty:
        return None
    return _records(df.head(1))[0]


def weather_forecast(hours: int = 72) -> list[dict[str, Any]]:
    df = _read_parquet_safe(PROCESSED_ROOT / "weather_kamloops_hourly.parquet")
    if df is None:
        return []
    if "is_forecast" in df.columns:
        df = df[df["is_forecast"]]
    return _records(df.head(hours))


def fwi_today() -> list[dict[str, Any]]:
    return _records(_read_parquet_safe(PROCESSED_ROOT / "fwi_stations_today.parquet"))


def aqhi_current(within_km: float = 100.0) -> list[dict[str, Any]]:
    df = _read_parquet_safe(PROCESSED_ROOT / "aqhi_kamloops_recent.parquet")
    if df is None:
        return []
    if "observation_datetime_utc" in df.columns:
        df = df.sort_values("observation_datetime_utc", ascending=False)
        # Latest reading per station.
        df = df.drop_duplicates(subset=["station_id"], keep="first")
    return _records(df)


def aqhi_history(days: int = 30) -> list[dict[str, Any]]:
    df = _read_parquet_safe(PROCESSED_ROOT / "aqhi_kamloops_recent.parquet")
    if df is None:
        return []
    if "observation_datetime_utc" in df.columns:
        df = df.copy()
        df["_ts"] = pd.to_datetime(df["observation_datetime_utc"], errors="coerce", utc=True)
        cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=days)
        df = df[df["_ts"].notna() & (df["_ts"] >= cutoff)]
        df = df.drop(columns=["_ts"])
    return _records(df)


def aq_pollutants_latest() -> dict[str, Any] | None:
    df = _read_parquet_safe(PROCESSED_ROOT / "aq_pollutants_recent.parquet")
    if df is None or df.empty:
        return None
    if "fetched_at_utc" in df.columns:
        df = df.sort_values("fetched_at_utc", ascending=False)
    return _records(df.head(1))[0]


def smoke_forecast_metadata() -> list[dict[str, Any]]:
    return _records(_read_parquet_safe(PROCESSED_ROOT / "smoke_forecast_metadata.parquet"))


def evac_active() -> list[dict[str, Any]]:
    return _records(_read_parquet_safe(PROCESSED_ROOT / "evac_active.parquet"))


def climate_projections(ssp: str | None = None, var: str | None = None) -> list[dict[str, Any]]:
    df = _read_parquet_safe(PROCESSED_ROOT / "climate_projections.parquet")
    if df is None:
        return []
    if ssp and "ssp" in df.columns:
        df = df[df["ssp"] == ssp]
    if var and "variable" in df.columns:
        df = df[df["variable"] == var]
    return _records(df)


def fires_seasonal_summary() -> list[dict[str, Any]]:
    """Aggregate historical fires by year — used by /api/climate/seasonal."""
    df = _read_parquet_safe(PROCESSED_ROOT / "fires_historical.parquet")
    if df is None:
        return []
    if "fire_year" not in df.columns or "hectares" not in df.columns:
        return []
    grouped = (
        df.groupby("fire_year")
        .agg(
            area_burned_ha=("hectares", "sum"),
            fire_count=("fire_id", "count"),
            largest_fire_ha=("hectares", "max"),
        )
        .reset_index()
        .rename(columns={"fire_year": "year"})
        .sort_values("year")
    )
    return _records(grouped)
