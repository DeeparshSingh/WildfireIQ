"""Runtime inference for the wildfire risk model (multi-region).

The trained model + isotonic calibrator are loaded once. For each modelled
region we:
  1. Read that region's latest daily weather and enrich it (FWI + lags).
  2. Predict P(fire-day) for the region, then calibrate.
  3. Multiply by each of the region's H3 cells' historical weight.
  4. Bucket into Low / Moderate / High / Extreme.

The grid returned to the frontend is the union of every region's cells,
each tagged with its region so the UI can filter by city.
"""

from __future__ import annotations

import json
from functools import lru_cache

import joblib
import lightgbm as lgb
import pandas as pd

from ..constants import REGIONS
from ..paths import MODELS_ROOT, PROCESSED_ROOT
from .features import _enrich_weather
from .train_risk import FEATURE_COLS

ART_DIR = MODELS_ROOT / "wildfire_risk_v1"


@lru_cache(maxsize=1)
def _load_artifacts() -> tuple[lgb.Booster, object, list[str]] | None:
    model_path = ART_DIR / "model.txt"
    cal_path = ART_DIR / "calibrator.joblib"
    feats_path = ART_DIR / "features.json"
    if not model_path.exists() or not cal_path.exists():
        return None
    booster = lgb.Booster(model_file=str(model_path))
    calibrator = joblib.load(cal_path)
    feats = json.loads(feats_path.read_text())
    return booster, calibrator, feats


@lru_cache(maxsize=1)
def _load_density() -> pd.DataFrame | None:
    p = PROCESSED_ROOT / "cell_density.parquet"
    if not p.exists():
        return None
    return pd.read_parquet(p)


_CLASS_ORDER = ["Low", "Moderate", "High", "Extreme"]


def _bucket(prob: float) -> str:
    if prob < 0.05:
        return "Low"
    if prob < 0.20:
        return "Moderate"
    if prob < 0.50:
        return "High"
    return "Extreme"


def _region_risk_level(cell_classes: list[str], min_share: float = 0.15) -> str:
    """Summarise a region by the highest risk class that covers at least
    `min_share` of its cells. This matches what the map actually shows for
    that city, so a single outlier hexagon does not flip the whole region."""
    n = len(cell_classes)
    if n == 0:
        return "Low"
    counts = {c: cell_classes.count(c) for c in set(cell_classes)}
    level = "Low"
    for cls in _CLASS_ORDER:
        if counts.get(cls, 0) / n >= min_share:
            level = cls
    return level


def cffdrs_class_for(fwi: float | None) -> str:
    """Canonical CFFDRS Fire Danger class from a region's FWI value.

    Standard CFFDRS thresholds (Van Wagner 1987; BC Wildfire Service public
    Fire Danger Rating uses the same boundaries):
        FWI <= 1   -> Low
        FWI 2-4    -> Moderate
        FWI 5-12   -> High
        FWI 13-20  -> Very High
        FWI >= 21  -> Extreme
    """
    if fwi is None or (isinstance(fwi, float) and fwi != fwi):  # NaN
        return "Unknown"
    if fwi <= 1:
        return "Low"
    if fwi <= 4:
        return "Moderate"
    if fwi <= 12:
        return "High"
    if fwi <= 20:
        return "Very High"
    return "Extreme"


def _region_today_row(weather_file: str, region_fire_rate: float) -> pd.DataFrame | None:
    """Enrich a region's daily weather and return its latest usable day."""
    path = PROCESSED_ROOT / weather_file
    if not path.exists():
        return None
    enriched = _enrich_weather(pd.read_parquet(path))
    if enriched.empty:
        return None
    enriched["region_fire_rate"] = region_fire_rate
    row = enriched.iloc[[-1]].dropna(subset=FEATURE_COLS)
    return row if not row.empty else None


def predict_grid() -> dict | None:
    """Compute the current risk grid across every region."""
    art = _load_artifacts()
    density = _load_density()
    if art is None or density is None:
        return None
    booster, calibrator, _ = art

    # Base rate per region (constant) from the density table.
    rate_by_region = (
        density.groupby("region")["region_fire_rate"].first().to_dict()
        if "region_fire_rate" in density.columns
        else {}
    )

    cells: list[dict] = []
    region_summaries: list[dict] = []
    primary: dict | None = None  # Thompson-Okanagan, for backward-compatible top level

    for reg in REGIONS:
        key = reg["key"]
        row = _region_today_row(reg["weather_file"], float(rate_by_region.get(key, 0.0)))
        if row is None:
            continue

        p_raw = float(booster.predict(row[FEATURE_COLS])[0])
        p_cal = float(calibrator.predict([p_raw])[0])
        fwi_today = float(row.iloc[0].get("fwi", float("nan")))
        cffdrs = cffdrs_class_for(fwi_today)
        obs_day = (
            row.iloc[0]["day_local"].isoformat()
            if hasattr(row.iloc[0]["day_local"], "isoformat")
            else str(row.iloc[0]["day_local"])
        )

        region_cells = density[density["region"] == key]
        region_classes: list[str] = []
        for _, c in region_cells.iterrows():
            cell_risk = p_cal * float(c["weight"])
            cls = _bucket(cell_risk)
            region_classes.append(cls)
            cells.append(
                {
                    "h3_cell": c["h3_cell"],
                    "region": key,
                    "region_label": reg["label"],
                    "centroid_lat": float(c["centroid_lat"]),
                    "centroid_lon": float(c["centroid_lon"]),
                    "hist_fire_count": int(c["hist_fire_count"]),
                    "p_region": p_cal,
                    "p_cell": cell_risk,
                    "risk_class": cls,
                }
            )

        summary = {
            "key": key,
            "label": reg["label"],
            "lat": reg["lat"],
            "lon": reg["lon"],
            "p_region": p_cal,
            "p_region_raw": p_raw,
            "fwi_today": fwi_today,
            # Map-derived AI risk level for the region (matches the hexagons
            # the user sees). The raw CFFDRS fire-weather class is kept
            # separately for reference.
            "risk_level": _region_risk_level(region_classes),
            "cffdrs_class": cffdrs,
            "observation_day": obs_day,
            "n_cells": int(len(region_cells)),
        }
        region_summaries.append(summary)
        if key == "thompson_okanagan":
            primary = summary

    if not cells:
        return None

    head = primary or region_summaries[0]
    return {
        # Top-level fields mirror the primary region for backward compatibility.
        "observation_day": head["observation_day"],
        "p_region": head["p_region"],
        "p_region_raw": head["p_region_raw"],
        "fwi_today": head["fwi_today"],
        "cffdrs_class": head["cffdrs_class"],
        "regions": region_summaries,
        "cells": cells,
    }


def predict_today_for_cell(h3_cell: str) -> dict | None:
    grid = predict_grid()
    if grid is None:
        return None
    for c in grid["cells"]:
        if c["h3_cell"] == h3_cell:
            return {**c, "observation_day": grid["observation_day"]}
    return None
