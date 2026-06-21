"""Feature engineering for the wildfire risk classifier.

Inputs (Parquet files in data/processed/):
  - per-region daily weather archives (1999-today)
  - fires_historical.parquet  (province-wide BC fire records, 1999-today)

Outputs:
  - features_risk_daily.parquet  (pooled per-region, per-day rows + label)
  - cell_density.parquet         (per H3 r=5 cell historical fire count,
                                  tagged with the region that owns it)

The model is trained on all regions pooled. Each row carries its region's
own local weather plus a `region_fire_rate` prior (that region's long-run
fire-day frequency), so one shared model captures both the universal
weather-to-fire relationship and the very different base rates between,
say, the dry Interior and the wet Lower Mainland.
"""

from __future__ import annotations

from pathlib import Path

import h3
import numpy as np
import pandas as pd

from ..constants import REGIONS
from ..paths import PROCESSED_ROOT
from .fwi import compute_fwi

H3_RES = 5  # ~250 km² hexagons

# Base rate (region_fire_rate) is computed from training years only so the
# held-out 2022/2023 evaluation stays clean.
BASE_RATE_MAX_YEAR = 2021


# ─── Weather features ───────────────────────────────────────────────


def _enrich_weather(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["day_local"] = pd.to_datetime(df["day_local"])
    df = df.sort_values("day_local").reset_index(drop=True)

    df = compute_fwi(df)

    for col in ["temp_max_c", "rh_min_pct", "wind_max_kmh", "precip_mm", "vpd_max_kpa"]:
        df[f"{col}_lag1"] = df[col].shift(1)
        df[f"{col}_lag7"] = df[col].shift(7)
        df[f"{col}_mean7"] = df[col].rolling(7, min_periods=1).mean()
        df[f"{col}_mean30"] = df[col].rolling(30, min_periods=1).mean()

    df["precip_sum7"] = df["precip_mm"].rolling(7, min_periods=1).sum()
    df["precip_sum30"] = df["precip_mm"].rolling(30, min_periods=1).sum()

    rain_flags = (df["precip_mm"] >= 1.0).astype(int)
    counter = 0
    out = []
    for f in rain_flags:
        counter = 0 if f else counter + 1
        out.append(counter)
    df["dry_spell_days"] = out

    doy = df["day_local"].dt.dayofyear
    df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    df["month"] = df["day_local"].dt.month
    df["year"] = df["day_local"].dt.year

    return df


# ─── Fire labels (per region bbox) ──────────────────────────────────


def _fires_in_bbox(fires: pd.DataFrame, bbox: tuple[float, float, float, float]) -> pd.DataFrame:
    w, s, e, n = bbox
    f = fires.dropna(subset=["latitude", "longitude"])
    return f[
        (f["latitude"] >= s) & (f["latitude"] <= n) & (f["longitude"] >= w) & (f["longitude"] <= e)
    ]


def _label_fires(weather: pd.DataFrame, region_fires: pd.DataFrame) -> pd.DataFrame:
    """Add `had_fire` + `n_fires` per day for fires already scoped to a region."""
    f = region_fires.copy()
    f["day_local"] = pd.to_datetime(f["discovery_date_utc"], errors="coerce")
    f = f.dropna(subset=["day_local"])
    f["day_local"] = f["day_local"].dt.tz_localize(None).dt.normalize()

    counts = f.groupby("day_local").size().rename("n_fires").reset_index()
    weather = weather.merge(counts, on="day_local", how="left")
    weather["n_fires"] = weather["n_fires"].fillna(0).astype(int)
    weather["had_fire"] = (weather["n_fires"] > 0).astype(int)
    return weather


# ─── Per-cell historical density ────────────────────────────────────


def _cells_in_bbox(bbox: tuple[float, float, float, float]) -> list[str]:
    """Enumerate every H3 r=5 cell intersecting a bbox via a fine grid scan."""
    w, s, e, n = bbox
    cells: set[str] = set()
    lat = s
    while lat <= n:
        lon = w
        while lon <= e:
            cells.add(h3.latlng_to_cell(lat, lon, H3_RES))
            lon += 0.05
        lat += 0.05
    return sorted(cells)


def _region_density(region_fires: pd.DataFrame, cell_ids: list[str]) -> pd.DataFrame:
    """Count historical fires per H3 cell within a region's claimed cells."""
    f = region_fires.dropna(subset=["latitude", "longitude"]).copy()
    f["h3_cell"] = [
        h3.latlng_to_cell(lat, lon, H3_RES)
        for lat, lon in zip(f["latitude"], f["longitude"], strict=True)
    ]
    counts = f.groupby("h3_cell").size().rename("hist_fire_count")

    grid = pd.DataFrame({"h3_cell": cell_ids})
    grid = grid.merge(counts, on="h3_cell", how="left").fillna({"hist_fire_count": 0})
    grid["hist_fire_count"] = grid["hist_fire_count"].astype(int)
    max_count = grid["hist_fire_count"].max() or 1
    grid["weight"] = (grid["hist_fire_count"] / max_count) ** 0.5
    return grid


# ─── Build ──────────────────────────────────────────────────────────


def build_features() -> dict[str, Path]:
    """Build pooled features + per-region density across all REGIONS."""
    fires = pd.read_parquet(PROCESSED_ROOT / "fires_historical.parquet")

    feature_frames: list[pd.DataFrame] = []
    density_frames: list[pd.DataFrame] = []
    claimed: set[str] = set()  # cells claimed by an earlier region win

    for reg in REGIONS:
        wpath = PROCESSED_ROOT / reg["weather_file"]
        if not wpath.exists():
            continue
        region_fires = _fires_in_bbox(fires, reg["bbox"])

        # Per-day features for this region.
        enriched = _enrich_weather(pd.read_parquet(wpath))
        labeled = _label_fires(enriched, region_fires)
        base_rate = float(
            labeled.loc[labeled["year"] <= BASE_RATE_MAX_YEAR, "had_fire"].mean()
        )
        labeled["region"] = reg["key"]
        labeled["region_fire_rate"] = base_rate
        feature_frames.append(labeled)

        # Density over this region's unclaimed cells.
        cell_ids = [c for c in _cells_in_bbox(reg["bbox"]) if c not in claimed]
        claimed.update(cell_ids)
        dens = _region_density(region_fires, cell_ids)
        dens["region"] = reg["key"]
        dens["region_label"] = reg["label"]
        dens["region_fire_rate"] = base_rate
        centroids = [h3.cell_to_latlng(c) for c in dens["h3_cell"]]
        dens["centroid_lat"] = [c[0] for c in centroids]
        dens["centroid_lon"] = [c[1] for c in centroids]
        density_frames.append(dens)

    pooled = pd.concat(feature_frames, ignore_index=True)
    grid = pd.concat(density_frames, ignore_index=True)

    out_features = PROCESSED_ROOT / "features_risk_daily.parquet"
    out_density = PROCESSED_ROOT / "cell_density.parquet"
    pooled.to_parquet(out_features, compression="zstd", index=False)
    grid.to_parquet(out_density, compression="zstd", index=False)
    return {"features": out_features, "density": out_density}


if __name__ == "__main__":
    paths = build_features()
    for k, p in paths.items():
        print(f"{k}: {p}  ({p.stat().st_size // 1024} KB)")
