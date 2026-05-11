"""Feature engineering for the wildfire risk classifier.

Inputs (Parquet files in data/processed/):
  - weather_kamloops_archive_daily.parquet  (~9,990 daily rows, 1999-today)
  - fires_historical.parquet               (~16k BC fire records, 1999–2025)

Outputs:
  - features_risk_daily.parquet  (per-day feature row + label `had_fire`)
  - cell_density.parquet         (per H3 r=5 cell historical fire-day count)
"""

from __future__ import annotations

import math
from pathlib import Path

import h3
import numpy as np
import pandas as pd

from ..constants import BBOX_EAST, BBOX_NORTH, BBOX_SOUTH, BBOX_WEST
from ..paths import PROCESSED_ROOT
from .fwi import compute_fwi


H3_RES = 5  # ~250 km² hexagons — ~180 cells over Thompson-Okanagan


# ─── Weather features ───────────────────────────────────────────────


def _enrich_weather(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["day_local"] = pd.to_datetime(df["day_local"])
    df = df.sort_values("day_local").reset_index(drop=True)

    # FWI from Van Wagner equations.
    df = compute_fwi(df)

    # Lags + rolling features (chronological).
    for col in ["temp_max_c", "rh_min_pct", "wind_max_kmh", "precip_mm", "vpd_max_kpa"]:
        df[f"{col}_lag1"] = df[col].shift(1)
        df[f"{col}_lag7"] = df[col].shift(7)
        df[f"{col}_mean7"] = df[col].rolling(7, min_periods=1).mean()
        df[f"{col}_mean30"] = df[col].rolling(30, min_periods=1).mean()

    # Rolling precip totals (drought signal).
    df["precip_sum7"] = df["precip_mm"].rolling(7, min_periods=1).sum()
    df["precip_sum30"] = df["precip_mm"].rolling(30, min_periods=1).sum()

    # Days-since-last-meaningful-rain (>= 1 mm) — classic drought indicator.
    rain_flags = (df["precip_mm"] >= 1.0).astype(int)
    counter = 0
    out = []
    for f in rain_flags:
        counter = 0 if f else counter + 1
        out.append(counter)
    df["dry_spell_days"] = out

    # Calendar features.
    doy = df["day_local"].dt.dayofyear
    df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    df["month"] = df["day_local"].dt.month
    df["year"] = df["day_local"].dt.year

    return df


# ─── Fire labels (Thompson-Okanagan focus) ─────────────────────────


def _label_fires(weather: pd.DataFrame, fires: pd.DataFrame) -> pd.DataFrame:
    """Add `had_fire` binary label + `n_fires` count to each day, scoped to
    the Thompson-Okanagan bbox."""
    f = fires.copy()
    f = f[
        (f["latitude"] >= BBOX_SOUTH)
        & (f["latitude"] <= BBOX_NORTH)
        & (f["longitude"] >= BBOX_WEST)
        & (f["longitude"] <= BBOX_EAST)
    ]
    f["day_local"] = pd.to_datetime(f["discovery_date_utc"], errors="coerce")
    f = f.dropna(subset=["day_local"])
    f["day_local"] = f["day_local"].dt.tz_localize(None).dt.normalize()

    counts = f.groupby("day_local").size().rename("n_fires").reset_index()
    weather = weather.merge(counts, on="day_local", how="left")
    weather["n_fires"] = weather["n_fires"].fillna(0).astype(int)
    weather["had_fire"] = (weather["n_fires"] > 0).astype(int)
    return weather


# ─── Per-cell historical density (Thompson-Okanagan only) ───────────


def _compute_cell_density(fires: pd.DataFrame) -> pd.DataFrame:
    """For each H3 r=5 cell in Thompson-Okanagan, count historical fire-days.
    These weights modulate the region-level risk probability to produce the
    per-cell display grid."""
    f = fires.copy()
    f = f[
        (f["latitude"] >= BBOX_SOUTH)
        & (f["latitude"] <= BBOX_NORTH)
        & (f["longitude"] >= BBOX_WEST)
        & (f["longitude"] <= BBOX_EAST)
    ]
    f = f.dropna(subset=["latitude", "longitude"])
    f["h3_cell"] = [
        h3.latlng_to_cell(lat, lon, H3_RES)
        for lat, lon in zip(f["latitude"], f["longitude"], strict=True)
    ]
    density = f.groupby("h3_cell").size().rename("hist_fire_count").reset_index()
    # Normalize to 0..1 weight; smooth so cells with one fire still register.
    max_count = density["hist_fire_count"].max() or 1
    density["weight"] = (density["hist_fire_count"] / max_count) ** 0.5
    return density


def _all_thompson_okanagan_cells() -> list[str]:
    """Enumerate every H3 r=5 cell intersecting the Thompson-Okanagan bbox.
    Uses a fine lat/lon grid + dedupe."""
    cells = set()
    lat_step = 0.05
    lon_step = 0.05
    lat = BBOX_SOUTH
    while lat <= BBOX_NORTH:
        lon = BBOX_WEST
        while lon <= BBOX_EAST:
            cells.add(h3.latlng_to_cell(lat, lon, H3_RES))
            lon += lon_step
        lat += lat_step
    return sorted(cells)


def build_features() -> dict[str, Path]:
    """Build all feature artifacts and write them to data/processed/."""
    weather = pd.read_parquet(PROCESSED_ROOT / "weather_kamloops_archive_daily.parquet")
    fires = pd.read_parquet(PROCESSED_ROOT / "fires_historical.parquet")

    enriched = _enrich_weather(weather)
    labeled = _label_fires(enriched, fires)

    density = _compute_cell_density(fires)
    # Expand to all bbox cells (cells with no historical fires get weight=0).
    all_cells = _all_thompson_okanagan_cells()
    grid = pd.DataFrame({"h3_cell": all_cells})
    grid = grid.merge(density, on="h3_cell", how="left").fillna({"hist_fire_count": 0, "weight": 0.0})

    # Add the centroid lat/lon for each cell so the frontend can render hexes.
    centroids = [h3.cell_to_latlng(c) for c in grid["h3_cell"]]
    grid["centroid_lat"] = [c[0] for c in centroids]
    grid["centroid_lon"] = [c[1] for c in centroids]

    out_features = PROCESSED_ROOT / "features_risk_daily.parquet"
    out_density = PROCESSED_ROOT / "cell_density.parquet"
    labeled.to_parquet(out_features, compression="zstd", index=False)
    grid.to_parquet(out_density, compression="zstd", index=False)
    return {"features": out_features, "density": out_density}


if __name__ == "__main__":
    paths = build_features()
    for k, p in paths.items():
        print(f"{k}: {p}  ({p.stat().st_size // 1024} KB)")
