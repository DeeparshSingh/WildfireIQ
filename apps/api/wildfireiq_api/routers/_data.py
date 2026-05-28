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


def fires_current(include_extinguished: bool = False) -> list[dict[str, Any]]:
    df = _read_parquet_safe(PROCESSED_ROOT / "fires_current.parquet")
    if df is None:
        return []
    if not include_extinguished and "status" in df.columns:
        # Drop fires with an explicit "Out" status — they are no longer burning.
        df = df[~df["status"].fillna("").str.strip().str.lower().isin({"out", "extinguished"})]
    return _records(df)


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
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=since_hours)
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
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
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
    """Return smoke timesteps joined with our Open-Meteo CAMS PM2.5 forecast at
    Kamloops centroid, so the modal scrubber can show the actual µg/m³ value
    alongside each forecast hour. Without this, the WMS overlay is invisible
    when PM2.5 is low — a transparent PNG looks like "no data" to the user.
    """
    smoke = _read_parquet_safe(PROCESSED_ROOT / "smoke_forecast_metadata.parquet")
    if smoke is None or smoke.empty:
        return []
    aq = _read_parquet_safe(PROCESSED_ROOT / "aq_hourly_kamloops.parquet")
    if aq is not None and not aq.empty and "time_utc" in aq.columns:
        # Round smoke timestep to the hour and join to AQ's hourly grid.
        smoke = smoke.copy()
        smoke["_join"] = pd.to_datetime(smoke["valid_time_utc"], utc=True).dt.floor("h")
        aq = aq[["time_utc", "pm2_5"]].copy()
        aq["_join"] = pd.to_datetime(aq["time_utc"], utc=True).dt.floor("h")
        merged = smoke.merge(aq[["_join", "pm2_5"]], on="_join", how="left")
        merged = merged.rename(columns={"pm2_5": "pm25_at_kamloops"})
        merged = merged.drop(columns=["_join"], errors="ignore")
        return _records(merged)
    return _records(smoke)


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


def seasonal_metrics() -> list[dict[str, Any]]:
    """Per-year joined fire+weather+FWI metrics (Phase 6)."""
    df = _read_parquet_safe(PROCESSED_ROOT / "seasonal_metrics.parquet")
    return _records(df)


def season_context() -> dict[str, Any]:
    """Derived metrics for the Phase 5 right-column ticker.

    Returns:
      days_since_5mm_rain : last day with ≥5 mm precip in Kamloops daily wx
      peak_month_day      : (month, day) of the historical Thompson-Okanagan
                             fire-season peak (median date of area burned).
    """
    out: dict[str, Any] = {
        "days_since_5mm_rain": None,
        "peak_month": 7,
        "peak_day": 20,
        "peak_basis": "median day-of-year of area burned across 1999-2025 BC fires",
    }

    daily = _read_parquet_safe(PROCESSED_ROOT / "weather_kamloops_daily.parquet")
    if daily is not None and "precip_mm" in daily.columns and "day_local" in daily.columns:
        df = daily.copy()
        df["day_local"] = pd.to_datetime(df["day_local"], errors="coerce")
        df = df.dropna(subset=["day_local"]).sort_values("day_local")
        today_ts = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
        observed = df[(df.get("is_forecast", False) != True) & (df["day_local"] <= today_ts)]
        wet = observed[observed["precip_mm"] >= 5.0]
        if not wet.empty:
            last_wet = wet["day_local"].max()
            out["days_since_5mm_rain"] = int((today_ts - last_wet).days)

    hist = _read_parquet_safe(PROCESSED_ROOT / "fires_historical.parquet")
    if hist is not None and "discovery_date_utc" in hist.columns and "hectares" in hist.columns:
        h = hist.copy()
        h["d"] = pd.to_datetime(h["discovery_date_utc"], errors="coerce")
        h = h.dropna(subset=["d"])
        h["doy"] = h["d"].dt.dayofyear
        # area-weighted median day-of-year
        if not h.empty and h["hectares"].sum() > 0:
            sorted_h = h.sort_values("doy")
            cumw = sorted_h["hectares"].cumsum()
            half = sorted_h["hectares"].sum() / 2
            peak_doy = int(sorted_h.loc[cumw >= half, "doy"].iloc[0])
            peak_date = pd.Timestamp(year=2000, month=1, day=1) + pd.Timedelta(days=peak_doy - 1)
            out["peak_month"] = int(peak_date.month)
            out["peak_day"] = int(peak_date.day)

    return out


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
