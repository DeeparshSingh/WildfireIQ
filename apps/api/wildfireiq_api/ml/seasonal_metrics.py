"""Build the per-year `seasonal_metrics.parquet` for Phase 6.

One row per year (1999–today) joining:
  • Historical fires (DataBC PROT_HISTORICAL_FIRE_POLYS / current registry)
    aggregated per fire_year for the Thompson-Okanagan BBOX.
  • Open-Meteo archive daily weather at Kamloops Airport — July mean temp,
    July–August precip total, July–August mean VPD.
  • Van Wagner FWI computed over the daily weather archive — July–August
    max FWI per year + count of days with FWI ≥ 19 (extreme).

Run via:
    uv run python -m wildfireiq_api.ml.seasonal_metrics

Idempotent — overwrites the parquet each run.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .fwi import compute_fwi
from ..settings import get_settings


REPO_ROOT = Path(__file__).resolve().parents[4]
PROCESSED = REPO_ROOT / "data" / "processed"


def _fires_by_year(bbox: tuple[float, float, float, float]) -> pd.DataFrame:
    df = pd.read_parquet(PROCESSED / "fires_historical.parquet")
    w, s, e, n = bbox
    if {"latitude", "longitude"}.issubset(df.columns):
        df = df.dropna(subset=["latitude", "longitude"])
        df = df[(df.latitude.between(s, n)) & (df.longitude.between(w, e))]
    if df.empty:
        return pd.DataFrame()

    df["discovery_date_utc"] = pd.to_datetime(df["discovery_date_utc"], errors="coerce")
    df["doy"] = df["discovery_date_utc"].dt.dayofyear
    g = df.groupby("fire_year")
    agg = pd.DataFrame({
        "area_burned_ha": g["hectares"].sum(min_count=1),
        "fire_count": g["fire_id"].count(),
        "largest_fire_ha": g["hectares"].max(),
        "season_start_doy": g["doy"].min(),
        "season_end_doy": g["doy"].max(),
    }).reset_index().rename(columns={"fire_year": "year"})
    agg["season_length_days"] = agg["season_end_doy"] - agg["season_start_doy"]
    return agg


def _weather_metrics_by_year() -> pd.DataFrame:
    wx = pd.read_parquet(PROCESSED / "weather_kamloops_archive_daily.parquet").copy()
    wx["day_local"] = pd.to_datetime(wx["day_local"], errors="coerce")
    wx = wx.dropna(subset=["day_local"])
    wx["year"] = wx["day_local"].dt.year
    wx["month"] = wx["day_local"].dt.month

    jul = wx[wx.month == 7]
    julaug = wx[wx.month.isin([7, 8])]

    by_year = pd.DataFrame({
        "mean_jul_temp_c": jul.groupby("year")["temp_max_c"].mean(),
        "julaug_precip_mm": julaug.groupby("year")["precip_mm"].sum(min_count=1),
        "mean_julaug_vpd_kpa": julaug.groupby("year")["vpd_max_kpa"].mean()
            if "vpd_max_kpa" in julaug.columns
            else pd.Series(dtype=float),
    }).reset_index()
    return by_year


def _fwi_metrics_by_year() -> pd.DataFrame:
    wx = pd.read_parquet(PROCESSED / "weather_kamloops_archive_daily.parquet").copy()
    wx["day_local"] = pd.to_datetime(wx["day_local"], errors="coerce")
    wx = wx.dropna(subset=["day_local"])
    # Defaults for missing predictors so the Van Wagner port doesn't NaN-poison.
    if "wind_max_kmh" not in wx.columns:
        wx["wind_max_kmh"] = 10.0
    if "rh_min_pct" not in wx.columns:
        wx["rh_min_pct"] = 40.0
    wx["wind_max_kmh"] = wx["wind_max_kmh"].fillna(10.0)
    wx["rh_min_pct"] = wx["rh_min_pct"].fillna(40.0)
    wx["precip_mm"] = wx["precip_mm"].fillna(0.0)
    wx["temp_max_c"] = wx["temp_max_c"].ffill().fillna(15.0)

    fwi = compute_fwi(wx)
    fwi["year"] = fwi["day_local"].dt.year
    fwi["month"] = fwi["day_local"].dt.month
    season = fwi[fwi.month.isin([7, 8])]

    out = pd.DataFrame({
        "max_julaug_fwi": season.groupby("year")["fwi"].max(),
        "days_fwi_ge_19": fwi[fwi["fwi"] >= 19].groupby("year").size(),
    }).reset_index()
    # Years that never crossed 19: fill with 0 not NaN.
    out["days_fwi_ge_19"] = out["days_fwi_ge_19"].fillna(0).astype(int)
    return out


def build() -> Path:
    s = get_settings()
    bbox = (s.bbox_west, s.bbox_south, s.bbox_east, s.bbox_north)

    fires = _fires_by_year(bbox)
    wx = _weather_metrics_by_year()
    fwi = _fwi_metrics_by_year()

    # Outer-merge so we keep any year with at least one source.
    df = fires.merge(wx, on="year", how="outer").merge(fwi, on="year", how="outer")
    df = df.sort_values("year").reset_index(drop=True)

    # Clip to 1999+ (where DataBC's record begins) and exclude the current
    # incomplete year unless > Oct (so the chart isn't dragged down by a
    # half-finished season).
    today = pd.Timestamp.utcnow()
    cur_year = int(today.year)
    if today.month < 10:
        df = df[df.year < cur_year]
    df = df[df.year >= 1999].reset_index(drop=True)

    out = PROCESSED / "seasonal_metrics.parquet"
    df.to_parquet(out, index=False)
    return out


def _main() -> None:
    p = build()
    print(f"wrote {p} with {len(pd.read_parquet(p))} years")


if __name__ == "__main__":
    _main()
