"""Train the wildfire risk classifier.

Target: P(at least one fire ignites somewhere in Thompson-Okanagan today |
weather + FWI + temporal features).

Train: 1999-2021.  Val: 2022.  Test: 2023.  (Per project proposal.)

The classifier outputs a daily probability for the region. At inference time,
this is multiplied by each H3 r=5 cell's `weight` (sqrt-normalized historical
fire-day count) to produce a per-cell risk score, which is then bucketed:

  P × weight  <  0.05  → Low
  0.05–0.20            → Moderate
  0.20–0.50            → High
  ≥ 0.50               → Extreme
"""

from __future__ import annotations

import json

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)

from ..paths import MODELS_ROOT, PROCESSED_ROOT

FEATURE_COLS = [
    # current-day weather
    "temp_max_c", "temp_min_c", "rh_min_pct", "wind_max_kmh",
    "wind_gust_max_kmh", "precip_mm", "vpd_max_kpa", "et0_mm",
    # FWI codes
    "ffmc", "dmc", "dc", "isi", "bui", "fwi", "dsr",
    # lags
    "temp_max_c_lag1", "temp_max_c_lag7", "temp_max_c_mean7", "temp_max_c_mean30",
    "rh_min_pct_lag1", "rh_min_pct_lag7", "rh_min_pct_mean7", "rh_min_pct_mean30",
    "wind_max_kmh_lag1", "wind_max_kmh_lag7", "wind_max_kmh_mean7", "wind_max_kmh_mean30",
    "precip_mm_lag1", "precip_mm_lag7", "precip_mm_mean7", "precip_mm_mean30",
    "vpd_max_kpa_lag1", "vpd_max_kpa_lag7", "vpd_max_kpa_mean7", "vpd_max_kpa_mean30",
    # drought + precip totals
    "precip_sum7", "precip_sum30", "dry_spell_days",
    # calendar
    "doy_sin", "doy_cos", "month",
]
TARGET_COL = "had_fire"

PARAMS: dict[str, object] = {
    "objective": "binary",
    "metric": "binary_logloss",
    "learning_rate": 0.04,
    "num_leaves": 63,
    "min_data_in_leaf": 200,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.85,
    "bagging_freq": 5,
    "lambda_l2": 1.0,
    "verbose": -1,
    "seed": 7,
}


def main() -> None:
    df = pd.read_parquet(PROCESSED_ROOT / "features_risk_daily.parquet")
    df = df.dropna(subset=FEATURE_COLS + [TARGET_COL])
    df["year"] = pd.to_datetime(df["day_local"]).dt.year

    train = df[df["year"] <= 2021]
    val = df[df["year"] == 2022]
    test = df[df["year"] == 2023]
    print(f"split  → train {len(train)} · val {len(val)} · test {len(test)}")
    print(
        f"prior  → train {train[TARGET_COL].mean():.3f} · "
        f"val {val[TARGET_COL].mean():.3f} · test {test[TARGET_COL].mean():.3f}"
    )

    X_train, y_train = train[FEATURE_COLS], train[TARGET_COL]
    X_val, y_val = val[FEATURE_COLS], val[TARGET_COL]
    X_test, y_test = test[FEATURE_COLS], test[TARGET_COL]

    train_set = lgb.Dataset(X_train, label=y_train)
    val_set = lgb.Dataset(X_val, label=y_val, reference=train_set)

    booster = lgb.train(
        PARAMS,
        train_set,
        num_boost_round=2000,
        valid_sets=[train_set, val_set],
        valid_names=["train", "val"],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
    )

    # Calibrate with isotonic regression on val probabilities.
    p_val_raw = booster.predict(X_val)
    calibrator = IsotonicRegression(out_of_bounds="clip").fit(p_val_raw, y_val)

    p_test_raw = booster.predict(X_test)
    p_test_cal = calibrator.predict(p_test_raw)

    metrics = {
        "n_train": len(train),
        "n_val": len(val),
        "n_test": len(test),
        "best_iter": int(booster.best_iteration or PARAMS.get("num_iterations", 0)),
        "val_pr_auc_raw": float(average_precision_score(y_val, p_val_raw)),
        "val_roc_auc_raw": float(roc_auc_score(y_val, p_val_raw)),
        "val_logloss_raw": float(log_loss(y_val, p_val_raw)),
        "test_pr_auc_raw": float(average_precision_score(y_test, p_test_raw)),
        "test_pr_auc_calibrated": float(average_precision_score(y_test, p_test_cal)),
        "test_roc_auc_raw": float(roc_auc_score(y_test, p_test_raw)),
        "test_brier_raw": float(brier_score_loss(y_test, p_test_raw)),
        "test_brier_calibrated": float(brier_score_loss(y_test, p_test_cal)),
        "test_logloss_calibrated": float(log_loss(y_test, p_test_cal)),
    }

    # Baselines for comparison.
    fwi_threshold = (X_test["fwi"].fillna(0) >= 19).astype(float)
    metrics["baseline_fwi_thresh_pr_auc"] = float(
        average_precision_score(y_test, fwi_threshold)
    )
    metrics["baseline_climatology_pr_auc"] = float(
        average_precision_score(y_test, np.full(len(y_test), y_train.mean()))
    )

    # Calibration reliability diagram (10 bins).
    frac_pos, mean_pred = calibration_curve(y_test, p_test_cal, n_bins=10, strategy="quantile")
    metrics["calibration_bins"] = [
        {"mean_pred": float(m), "frac_pos": float(f)}
        for m, f in zip(mean_pred, frac_pos, strict=True)
    ]

    # Feature importance (gain).
    importances = booster.feature_importance(importance_type="gain")
    metrics["feature_importance"] = sorted(
        [
            {"feature": f, "gain": float(g)}
            for f, g in zip(FEATURE_COLS, importances, strict=True)
        ],
        key=lambda x: -x["gain"],
    )[:20]

    print(json.dumps({k: v for k, v in metrics.items() if not isinstance(v, list)}, indent=2))

    # Save artifacts.
    MODELS_ROOT.mkdir(parents=True, exist_ok=True)
    art_dir = MODELS_ROOT / "wildfire_risk_v1"
    art_dir.mkdir(exist_ok=True)
    booster.save_model(str(art_dir / "model.txt"))
    joblib.dump(calibrator, art_dir / "calibrator.joblib")
    (art_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (art_dir / "features.json").write_text(json.dumps(FEATURE_COLS, indent=2))
    print(f"\nsaved → {art_dir}")


if __name__ == "__main__":
    main()
