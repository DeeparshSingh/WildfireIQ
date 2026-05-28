"""Train the 48-hour air-quality (PM2.5) forecaster.

One LightGBM **quantile** model per horizon in {1, 3, 6, 12, 24, 36, 48} hours,
× three quantile levels {0.10, 0.50, 0.90}. At inference, the frontend
renders the q10-q90 band as a soft uncertainty halo around the q50 median
line.

Why per-horizon instead of a recurrent / sequence model: avoids error
compounding, trains in seconds, and the band shows the model getting less
certain further out — exactly the right inductive bias for a 48 h horizon.

Why quantile rather than just predicting a number: smoke events are bimodal
(most hours are clean; some are very bad). A point forecast hides that;
quantile bands surface it.

Data: `data/processed/aq_hourly_kamloops.parquet` (Open-Meteo air quality
archive + weather, ~2.2k hourly rows over the last 92 days).

Features per row: current PM2.5 + 6h-mean PM2.5, lagged PM2.5 (h-1, h-3,
h-6, h-12, h-24), co-located weather (temp, RH, wind speed + direction,
precip, boundary-layer height), and calendar (hour-of-day sin/cos,
day-of-week sin/cos).

Target: PM2.5 (µg/m³) at the prediction horizon.
Time-series train/test split — 80% chronological train, 20% holdout test.
"""

from __future__ import annotations

import json

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_pinball_loss

from ..paths import MODELS_ROOT, PROCESSED_ROOT

HORIZONS_H = [1, 3, 6, 12, 24, 36, 48]
QUANTILES = [0.10, 0.50, 0.90]

FEATURE_COLS_BASE = [
    "pm2_5",
    "pm2_5_lag1",
    "pm2_5_lag3",
    "pm2_5_lag6",
    "pm2_5_lag12",
    "pm2_5_lag24",
    "pm2_5_mean6",
    "pm2_5_mean24",
    "pm10",
    "o3",
    "no2",
    "temp_c",
    "rh_pct",
    "wind_kmh",
    "wind_dir",
    "precip_mm",
    "boundary_layer_m",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
]


def _enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc").reset_index(drop=True)

    # Lags + rolls
    for k in (1, 3, 6, 12, 24):
        df[f"pm2_5_lag{k}"] = df["pm2_5"].shift(k)
    df["pm2_5_mean6"] = df["pm2_5"].rolling(6, min_periods=1).mean()
    df["pm2_5_mean24"] = df["pm2_5"].rolling(24, min_periods=1).mean()

    # Calendar features
    hour = df["time_utc"].dt.hour
    dow = df["time_utc"].dt.dayofweek
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    df["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    return df


def _build_horizon_targets(df: pd.DataFrame, horizon_h: int) -> pd.DataFrame:
    """Returns a copy of df with a `y` column = PM2.5 at t+horizon_h hours."""
    out = df.copy()
    out["y"] = out["pm2_5"].shift(-horizon_h)
    return out


def main() -> None:
    src = PROCESSED_ROOT / "aq_hourly_kamloops.parquet"
    if not src.exists():
        raise SystemExit(
            "Run `--only open_meteo_aq_archive` first to populate hourly AQ data."
        )
    df = _enrich(pd.read_parquet(src))
    print(f"loaded {len(df)} hourly rows, "
          f"{df['time_utc'].min().date()} → {df['time_utc'].max().date()}")

    ART = MODELS_ROOT / "aq_forecaster_v1"
    ART.mkdir(parents=True, exist_ok=True)

    all_metrics: dict[str, dict] = {}

    for h in HORIZONS_H:
        df_h = _build_horizon_targets(df, h)
        df_h = df_h.dropna(subset=FEATURE_COLS_BASE + ["y"])
        cut = int(len(df_h) * 0.8)
        train = df_h.iloc[:cut]
        test = df_h.iloc[cut:]
        if len(train) < 200 or len(test) < 50:
            continue

        h_dir = ART / f"h{h}"
        h_dir.mkdir(exist_ok=True)
        h_metrics: dict[str, float] = {
            "n_train": len(train),
            "n_test": len(test),
        }

        for q in QUANTILES:
            booster = lgb.train(
                {
                    "objective": "quantile",
                    "alpha": q,
                    "learning_rate": 0.04,
                    "num_leaves": 31,
                    "min_data_in_leaf": 25,
                    "feature_fraction": 0.85,
                    "bagging_fraction": 0.85,
                    "bagging_freq": 5,
                    "lambda_l2": 1.0,
                    "verbose": -1,
                    "seed": 7,
                },
                lgb.Dataset(train[FEATURE_COLS_BASE], label=train["y"]),
                num_boost_round=500,
                callbacks=[lgb.log_evaluation(0)],
            )
            booster.save_model(str(h_dir / f"q{int(q*100):02d}.txt"))
            preds = booster.predict(test[FEATURE_COLS_BASE])
            pinball = mean_pinball_loss(test["y"], preds, alpha=q)
            h_metrics[f"q{int(q*100):02d}_pinball"] = float(pinball)
            if abs(q - 0.5) < 1e-6:
                h_metrics["q50_mae"] = float(mean_absolute_error(test["y"], preds))

        # Persistence baseline: predict y = current pm2_5.
        baseline_mae = float(mean_absolute_error(test["y"], test["pm2_5"]))
        h_metrics["baseline_persistence_mae"] = baseline_mae

        all_metrics[f"h{h}"] = h_metrics
        print(
            f"  h={h:>2}h  test MAE q50 {h_metrics['q50_mae']:.2f} "
            f"(persistence {baseline_mae:.2f})"
        )

    (ART / "metrics.json").write_text(json.dumps(all_metrics, indent=2))
    (ART / "features.json").write_text(json.dumps(FEATURE_COLS_BASE, indent=2))
    print(f"\nsaved → {ART}")


if __name__ == "__main__":
    main()
