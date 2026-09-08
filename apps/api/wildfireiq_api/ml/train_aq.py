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

The q10-q90 band is then **conformalised**. Quantile gradient boosting fits
each quantile independently and regularises each toward the conditional centre,
so the outer quantiles pull inward and a nominally 80% band under-covers — this
model measured 59-68% uncalibrated. Conformalized quantile regression (Romano,
Patterson and Candes, 2019) corrects it with one number per horizon: score the
band against data the fit never saw, take the (1-alpha) quantile of the
worst-case violation, and widen by it. The score is normalised by band width,
so the correction is multiplicative and a confident hour keeps a tight band
while an uncertain one widens — which is the point of showing a band at all.

Data: `data/processed/aq_hourly_kamloops.parquet` — the Open-Meteo CAMS
air-quality archive with co-located weather. The nightly `open_meteo_aq_archive`
job extends it and nothing trims it, so it grows; training uses whatever the
file holds. A retrain after a long run therefore sees more history than the
shipped artifact did, and the model card records the corpus span its published
figures belong to.

Features per row: current PM2.5 + 6h-mean PM2.5, lagged PM2.5 (h-1, h-3,
h-6, h-12, h-24), co-located weather (temp, RH, wind speed + direction,
precip, boundary-layer height), and calendar (hour-of-day sin/cos,
day-of-week sin/cos).

Target: PM2.5 (µg/m³) at the prediction horizon.
Splits. The models are fitted on the first 70% of the record, chronologically,
so no future hour informs the fit. The remaining 30% is then split at random
into a calibration third and a test two-thirds.

Randomising that last step is deliberate and it matters. Conformal calibration
needs the calibration rows and the rows being predicted to be exchangeable. A
chronological calibration slice is not: on this record it lands in April-June
air averaging 6.8 ug/m3, while the holdout is the June-September fire season
averaging 21.6 with a peak of 185. Calibrating on the first and evaluating on
the second reached only 63-69% coverage. Drawing both from the same window
reaches 79-81%. See the model card for what that does and does not prove.
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

#: Nominal miscoverage of the q10-q90 band. 0.20 => a nominal 80% interval.
CONFORMAL_ALPHA = 0.20
#: Fraction of the held-out tail reserved for computing the conformal factor.
CONFORMAL_CALIB_SHARE = 1 / 3
#: Fixed so a retrain on the same input reproduces the same split exactly.
SPLIT_SEED = 7

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


def _split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Train / calibration / test. See the module docstring for why the last
    two are drawn at random from the tail rather than taken in order."""
    n = len(frame)
    train = frame.iloc[: int(n * 0.70)]
    tail = frame.iloc[int(n * 0.70) :]
    order = np.random.RandomState(SPLIT_SEED).permutation(len(tail))
    k = int(len(tail) * CONFORMAL_CALIB_SHARE)
    return train, tail.iloc[order[:k]], tail.iloc[order[k:]]


def _band(
    fitted: dict[int, lgb.Booster], frame: pd.DataFrame, factor: float
) -> tuple[np.ndarray, np.ndarray]:
    """The band a user would actually be shown: widened by `factor` times its
    own width, floored at zero, and ordered. Mirrors `ml.aq_infer` exactly, so
    the coverage this module reports is the coverage the chart delivers."""
    lo = fitted[10].predict(frame[FEATURE_COLS_BASE])
    hi = fitted[90].predict(frame[FEATURE_COLS_BASE])
    pad = factor * np.maximum(hi - lo, 0.0)
    lo, hi = np.maximum(0.0, lo - pad), np.maximum(0.0, hi + pad)
    return np.minimum(lo, hi), np.maximum(lo, hi)


def _conformal_factor(fitted: dict[int, lgb.Booster], calib: pd.DataFrame) -> float:
    """How much to widen the band, as a multiple of its own width.

    The conformity score is the signed distance outside the band, normalised by
    band width — negative when the truth fell inside. The factor is the
    ``ceil((n+1)(1-alpha))``-th smallest score, which is the finite-sample
    correction that gives at least ``1 - alpha`` coverage on exchangeable data.
    Clamped at zero: a band that already over-covers is left alone, because
    narrowing one would trade honesty for a tidier chart.
    """
    lo = fitted[10].predict(calib[FEATURE_COLS_BASE])
    hi = fitted[90].predict(calib[FEATURE_COLS_BASE])
    y = calib["y"].to_numpy(dtype=float)
    scores = np.maximum(lo - y, y - hi) / np.maximum(hi - lo, 1e-6)

    n = len(scores)
    rank = min(int(np.ceil((n + 1) * (1.0 - CONFORMAL_ALPHA))), n)
    return float(max(0.0, np.sort(scores)[rank - 1]))


def _band_coverage(fitted: dict[int, lgb.Booster], frame: pd.DataFrame, factor: float) -> float:
    """Fraction of `frame` whose truth lands inside the band."""
    lo, hi = _band(fitted, frame, factor)
    y = frame["y"].to_numpy(dtype=float)
    return float(((y >= lo) & (y <= hi)).mean())


def _band_width(fitted: dict[int, lgb.Booster], frame: pd.DataFrame, factor: float) -> float:
    """Mean band width in µg/m³ — the price paid for the coverage above."""
    lo, hi = _band(fitted, frame, factor)
    return float((hi - lo).mean())


def main() -> None:
    src = PROCESSED_ROOT / "aq_hourly_kamloops.parquet"
    if not src.exists():
        raise SystemExit("Run `--only open_meteo_aq_archive` first to populate hourly AQ data.")
    df = _enrich(pd.read_parquet(src))
    print(
        f"loaded {len(df)} hourly rows, "
        f"{df['time_utc'].min().date()} → {df['time_utc'].max().date()}"
    )

    ART = MODELS_ROOT / "aq_forecaster_v1"
    ART.mkdir(parents=True, exist_ok=True)

    all_metrics: dict[str, dict] = {}
    conformal_factors: dict[str, float] = {}

    for h in HORIZONS_H:
        df_h = _build_horizon_targets(df, h)
        df_h = df_h.dropna(subset=[*FEATURE_COLS_BASE, "y"])
        train, calib, test = _split(df_h)
        if len(train) < 200 or len(calib) < 50 or len(test) < 50:
            continue

        h_dir = ART / f"h{h}"
        h_dir.mkdir(exist_ok=True)
        h_metrics: dict[str, float] = {
            "n_train": len(train),
            "n_calib": len(calib),
            "n_test": len(test),
        }
        fitted: dict[int, lgb.Booster] = {}

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
                # 200, measured. On the full-year corpus the round count was
                # swept at 100 / 200 / 300 / 500: all four beat the persistence
                # baseline at the same five horizons, and 200 lands within 2%
                # of 500 on test MAE while producing boosters 2.5x smaller
                # (0.57 MB against 1.42 MB, times 21 models). Early stopping on
                # a carved-out validation slice was tried and was worse — it
                # costs 10% of the training data and stopped short, dropping to
                # three horizons better than persistence.
                num_boost_round=200,
                callbacks=[lgb.log_evaluation(0)],
            )
            booster.save_model(str(h_dir / f"q{int(q * 100):02d}.txt"))
            fitted[int(q * 100)] = booster
            preds = booster.predict(test[FEATURE_COLS_BASE])
            pinball = mean_pinball_loss(test["y"], preds, alpha=q)
            h_metrics[f"q{int(q * 100):02d}_pinball"] = float(pinball)
            if abs(q - 0.5) < 1e-6:
                h_metrics["q50_mae"] = float(mean_absolute_error(test["y"], preds))

        # Persistence baseline: predict y = current pm2_5.
        baseline_mae = float(mean_absolute_error(test["y"], test["pm2_5"]))
        h_metrics["baseline_persistence_mae"] = baseline_mae

        # ── Conformalise the band, then measure what it actually delivers ──
        factor = _conformal_factor(fitted, calib)
        conformal_factors[f"h{h}"] = factor
        h_metrics["conformal_factor"] = factor
        h_metrics["band_coverage_raw"] = _band_coverage(fitted, test, 0.0)
        h_metrics["band_coverage_calibrated"] = _band_coverage(fitted, test, factor)
        h_metrics["band_width_calibrated"] = _band_width(fitted, test, factor)

        all_metrics[f"h{h}"] = h_metrics
        print(
            f"  h={h:>2}h  MAE {h_metrics['q50_mae']:.2f} "
            f"(persistence {baseline_mae:.2f})  band "
            f"{h_metrics['band_coverage_raw'] * 100:.0f}% -> "
            f"{h_metrics['band_coverage_calibrated'] * 100:.0f}% "
            f"(x{1 + factor:.2f}, width {h_metrics['band_width_calibrated']:.1f})"
        )

    (ART / "metrics.json").write_text(json.dumps(all_metrics, indent=2))
    (ART / "features.json").write_text(json.dumps(FEATURE_COLS_BASE, indent=2))
    # Serving reads this; a missing file means "no widening", so an older
    # artifact set still loads and simply behaves as it did before.
    (ART / "conformal.json").write_text(
        json.dumps(
            {
                "method": "conformalized quantile regression, width-normalised (Romano et al. 2019)",
                "alpha": CONFORMAL_ALPHA,
                "nominal_coverage": round(1.0 - CONFORMAL_ALPHA, 4),
                "factors": conformal_factors,
                "measured_coverage": {
                    k: round(v["band_coverage_calibrated"], 4) for k, v in all_metrics.items()
                },
            },
            indent=2,
        )
    )
    print(f"\nsaved → {ART}")


if __name__ == "__main__":
    main()
