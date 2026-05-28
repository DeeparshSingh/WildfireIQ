"""Runtime inference for the wildfire risk model.

The trained model + isotonic calibrator are loaded once at FastAPI startup
(or lazily on first call). At inference time we:
  1. Pull today's + tomorrow's weather features (Open-Meteo current / forecast).
  2. Compute FWI carrying forward yesterday's codes (from cached state).
  3. Predict P(fire-day) for each day in the window.
  4. Multiply by each H3 r=5 cell's normalized historical weight.
  5. Bucket into Low / Moderate / High / Extreme.
"""

from __future__ import annotations

import json
from functools import lru_cache

import joblib
import lightgbm as lgb
import pandas as pd

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


def _bucket(prob: float) -> str:
    if prob < 0.05:
        return "Low"
    if prob < 0.20:
        return "Moderate"
    if prob < 0.50:
        return "High"
    return "Extreme"


def cffdrs_class_for(fwi: float | None) -> str:
    """Canonical CFFDRS Fire Danger class from today's FWI value.

    Standard CFFDRS thresholds (Van Wagner 1987; BC Wildfire Service public
    Fire Danger Rating uses the same boundaries):
        FWI ≤ 1     → Low
        FWI 2-4     → Moderate
        FWI 5-12    → High
        FWI 13-20   → Very High
        FWI ≥ 21    → Extreme
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


def _today_features() -> pd.DataFrame | None:
    """Enrich the archive weather and return the latest observed day (which
    drives the daily risk score). Forecast-fed risk for future days will
    land in a Phase 4 stretch — needs schema reconciliation between the
    Open-Meteo current/forecast columns and the ERA5 archive columns."""
    arch_path = PROCESSED_ROOT / "weather_kamloops_archive_daily.parquet"
    if not arch_path.exists():
        return None
    df = pd.read_parquet(arch_path)
    return _enrich_weather(df)


def predict_grid() -> dict | None:
    """Compute the current risk grid: one row per H3 r=5 cell with
    bucketed risk class + raw probability."""
    art = _load_artifacts()
    density = _load_density()
    if art is None or density is None:
        return None
    booster, calibrator, _ = art

    enriched = _today_features()
    if enriched is None or enriched.empty:
        return None
    today_row = enriched.iloc[[-1]]
    today_row = today_row.dropna(subset=FEATURE_COLS)
    if today_row.empty:
        return None

    X = today_row[FEATURE_COLS]
    p_raw = float(booster.predict(X)[0])
    p_cal = float(calibrator.predict([p_raw])[0])

    # Canonical CFFDRS class from today's FWI (Kamloops, derived via
    # Van Wagner). This is what BCWS publishes as the official Fire Danger.
    today_fwi = float(today_row.iloc[0].get("fwi", float("nan")))
    cffdrs = cffdrs_class_for(today_fwi)

    cells: list[dict] = []
    for _, c in density.iterrows():
        cell_risk = p_cal * float(c["weight"])
        cells.append(
            {
                "h3_cell": c["h3_cell"],
                "centroid_lat": float(c["centroid_lat"]),
                "centroid_lon": float(c["centroid_lon"]),
                "hist_fire_count": int(c["hist_fire_count"]),
                "p_region": p_cal,
                "p_cell": cell_risk,
                "risk_class": _bucket(cell_risk),
            }
        )

    obs_day = (
        today_row.iloc[0]["day_local"].isoformat()
        if hasattr(today_row.iloc[0]["day_local"], "isoformat")
        else str(today_row.iloc[0]["day_local"])
    )
    return {
        "observation_day": obs_day,
        "p_region": p_cal,
        "p_region_raw": p_raw,
        "fwi_today": today_fwi,
        "cffdrs_class": cffdrs,
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
