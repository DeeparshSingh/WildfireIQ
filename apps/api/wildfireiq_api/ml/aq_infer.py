"""Runtime inference for the 48-hour AQ forecaster.

Loads per-horizon, per-quantile LightGBM boosters once at startup. Builds
features from the latest enriched AQ row (Open-Meteo air quality + weather)
and predicts for each horizon × quantile.

Output rows: { time_utc, horizon_h, q10, q50, q90, aqhi_q50 }
"""

from __future__ import annotations

import json
from datetime import timedelta
from functools import lru_cache

import lightgbm as lgb
import numpy as np
import pandas as pd

from ..paths import MODELS_ROOT, PROCESSED_ROOT
from .train_aq import FEATURE_COLS_BASE, HORIZONS_H, QUANTILES, _enrich

ART = MODELS_ROOT / "aq_forecaster_v1"


@lru_cache(maxsize=1)
def _load_boosters() -> dict[tuple[int, int], lgb.Booster] | None:
    if not ART.exists():
        return None
    boosters: dict[tuple[int, int], lgb.Booster] = {}
    for h in HORIZONS_H:
        for q in QUANTILES:
            path = ART / f"h{h}" / f"q{int(q*100):02d}.txt"
            if not path.exists():
                return None
            boosters[(h, int(q * 100))] = lgb.Booster(model_file=str(path))
    return boosters


def pm25_to_aqhi(pm25: float) -> float:
    """Health Canada AQHI formula component for PM2.5 (µg/m³).

    AQHI = (1000 / 10.4) × (exp(0.000487 × PM2.5) - 1) (PM2.5 contribution).
    For full AQHI we'd need NO2 and O3 too. We approximate using just PM2.5
    since wildfire smoke is the dominant signal in our context.
    """
    return float((1000.0 / 10.4) * (np.exp(0.000487 * pm25) - 1.0))


def predict_forecast() -> dict | None:
    boosters = _load_boosters()
    if boosters is None:
        return None
    src = PROCESSED_ROOT / "aq_hourly_kamloops.parquet"
    if not src.exists():
        return None

    df = _enrich(pd.read_parquet(src))
    df = df.dropna(subset=FEATURE_COLS_BASE)
    if df.empty:
        return None

    # Use the latest available *observed* row (boundary between past + future).
    now = pd.Timestamp.now(tz="UTC").floor("h")
    obs = df[df["time_utc"] <= now]
    if obs.empty:
        obs = df
    latest = obs.iloc[[-1]]
    X = latest[FEATURE_COLS_BASE]
    base_time = latest["time_utc"].iloc[0]

    forecasts: list[dict] = []
    for h in HORIZONS_H:
        q10 = float(boosters[(h, 10)].predict(X)[0])
        q50 = float(boosters[(h, 50)].predict(X)[0])
        q90 = float(boosters[(h, 90)].predict(X)[0])
        # Quantile crossing fix: q10 ≤ q50 ≤ q90.
        q10, q50, q90 = sorted([max(0.0, q10), max(0.0, q50), max(0.0, q90)])
        forecasts.append(
            {
                "horizon_h": h,
                "time_utc": (base_time + timedelta(hours=h)).isoformat(),
                "q10": q10,
                "q50": q50,
                "q90": q90,
                "aqhi_q50": pm25_to_aqhi(q50),
            }
        )

    # Also return the trailing 12 observed hours so the chart has context
    # before "now".
    obs_recent = obs.tail(12)[["time_utc", "pm2_5"]].copy()
    obs_recent["time_utc"] = obs_recent["time_utc"].dt.tz_convert("UTC").dt.strftime(
        "%Y-%m-%dT%H:%M:%S%z"
    )
    observations = [
        {"time_utc": r["time_utc"], "pm2_5": float(r["pm2_5"])}
        for _, r in obs_recent.iterrows()
    ]

    metrics_path = ART / "metrics.json"
    metrics = (
        json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
    )

    return {
        "issued_at_utc": base_time.isoformat(),
        "observations": observations,
        "forecasts": forecasts,
        "metrics": metrics,
    }


def predict_calendar(days: int = 90) -> dict | None:
    """Per-day max PM2.5 (and approx AQHI) for the last N days, for the
    smoke-event calendar heatmap."""
    src = PROCESSED_ROOT / "aq_hourly_kamloops.parquet"
    if not src.exists():
        return None
    df = pd.read_parquet(src)
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    df = df[df["time_utc"] >= cutoff].copy()
    df["day_utc"] = df["time_utc"].dt.date
    daily = (
        df.groupby("day_utc")
        .agg(max_pm25=("pm2_5", "max"), mean_pm25=("pm2_5", "mean"))
        .reset_index()
        .sort_values("day_utc")
    )
    rows = [
        {
            "day_utc": str(r["day_utc"]),
            "max_pm25": float(r["max_pm25"]),
            "mean_pm25": float(r["mean_pm25"]),
            "max_aqhi": pm25_to_aqhi(float(r["max_pm25"])),
        }
        for _, r in daily.iterrows()
    ]
    return {"days": rows}
