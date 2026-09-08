"""Runtime inference for the 48-hour AQ forecaster.

Loads per-horizon, per-quantile LightGBM boosters once at startup. Builds
features from the latest enriched AQ row (Open-Meteo air quality + weather)
and predicts for each horizon × quantile.

The q10-q90 band is widened by the conformal factor the trainer measured for
that horizon, which is what makes it a calibrated ~80% interval rather than a
nominal one. `conformal.json` missing is not an error: the factor defaults to
zero and the band is served raw, so an artifact set from before calibration
still loads.

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
            path = ART / f"h{h}" / f"q{int(q * 100):02d}.txt"
            if not path.exists():
                return None
            boosters[(h, int(q * 100))] = lgb.Booster(model_file=str(path))
    return boosters


@lru_cache(maxsize=1)
def _load_conformal() -> dict[int, float]:
    """Per-horizon band-widening factors, keyed by horizon in hours."""
    path = ART / "conformal.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return {int(str(k).lstrip("h")): float(v) for k, v in (payload.get("factors") or {}).items()}


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

    conformal = _load_conformal()

    forecasts: list[dict] = []
    for h in HORIZONS_H:
        q10 = float(boosters[(h, 10)].predict(X)[0])
        q50 = float(boosters[(h, 50)].predict(X)[0])
        q90 = float(boosters[(h, 90)].predict(X)[0])
        # Conformal widening, as a multiple of the band's own width, so the
        # correction grows where the model is already unsure. `ml.train_aq`
        # measures the coverage this produces; keep the two in step.
        pad = conformal.get(h, 0.0) * max(q90 - q10, 0.0)
        q10, q90 = q10 - pad, q90 + pad
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
    obs_recent["time_utc"] = (
        obs_recent["time_utc"].dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    )
    observations = [
        {"time_utc": r["time_utc"], "pm2_5": float(r["pm2_5"])} for _, r in obs_recent.iterrows()
    ]

    metrics_path = ART / "metrics.json"
    metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}

    return {
        "issued_at_utc": base_time.isoformat(),
        "observations": observations,
        "forecasts": forecasts,
        "metrics": metrics,
        # So the chart can describe its own band from the model that produced
        # it, instead of a caption someone has to remember to update.
        "band": _band_metadata(metrics, conformal),
    }


def _band_metadata(metrics: dict, conformal: dict[int, float]) -> dict:
    """What the q10-q90 band means, measured rather than asserted."""
    measured = [
        m["band_coverage_calibrated"]
        for m in metrics.values()
        if isinstance(m, dict) and "band_coverage_calibrated" in m
    ]
    return {
        "nominal_coverage": 0.80,
        "measured_coverage": round(sum(measured) / len(measured), 4) if measured else None,
        "calibrated": bool(conformal),
        "method": "conformalized quantile regression" if conformal else None,
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
