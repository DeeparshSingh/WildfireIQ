"""Conformal calibration of the air-quality band.

The band the `/air-quality` chart draws is nominally an 80% interval. Quantile
gradient boosting does not deliver that on its own — uncalibrated it measured
57-66% — so the trainer computes a per-horizon widening factor and serving
applies it. These tests pin the parts of that where being wrong would be
invisible: the factor's arithmetic, the fact that serving widens the band by
exactly what the trainer measured, and graceful behaviour when the calibration
artifact is absent.

The maths tests are pure and always run. The artifact tests skip when the model
has not been trained on this checkout.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from wildfireiq_api.ml import aq_infer
from wildfireiq_api.ml.train_aq import (
    CONFORMAL_ALPHA,
    FEATURE_COLS_BASE,
    _conformal_factor,
    _split,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
ART = REPO_ROOT / "data" / "models" / "aq_forecaster_v1"


class _FixedBooster:
    """Returns a constant prediction, so the conformal arithmetic is checkable
    by hand rather than by trusting LightGBM."""

    def __init__(self, value: float) -> None:
        self.value = value

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return np.full(len(frame), self.value, dtype=float)


def _calib(truths: list[float]) -> pd.DataFrame:
    frame = pd.DataFrame({c: 0.0 for c in FEATURE_COLS_BASE}, index=range(len(truths)))
    frame["y"] = truths
    return frame


# ─── The factor's arithmetic ─────────────────────────────────────────


def test_a_band_that_already_covers_everything_is_left_alone() -> None:
    """Every truth inside [10, 20] means every conformity score is negative.
    Widening by a negative number would narrow the band, which would buy a
    tidier chart with a less honest one."""
    fitted = {10: _FixedBooster(10.0), 90: _FixedBooster(20.0)}
    assert _conformal_factor(fitted, _calib([12.0] * 50)) == 0.0


def test_the_factor_is_the_width_normalised_violation_quantile() -> None:
    """Band [0, 10] (width 10) with truths at 15 → every score is 0.5, so the
    factor must be 0.5: widening by half the width puts the band at [-5, 15]."""
    fitted = {10: _FixedBooster(0.0), 90: _FixedBooster(10.0)}
    assert _conformal_factor(fitted, _calib([15.0] * 60)) == pytest.approx(0.5)


def test_the_factor_spends_the_miscoverage_budget_before_it_widens() -> None:
    """An 80% interval is allowed to miss one row in five, so a tail smaller
    than that budget must not widen the band at all — the factor is the
    rank-based (1-alpha) quantile of the scores, never their maximum.

    The rank is ``ceil((n+1)(1-alpha))``, one place beyond the naive
    percentile. That extra place is the finite-sample correction, and it is
    why a tail of exactly alpha still widens: conformal errs toward
    over-covering, which is the safe direction for a health signal.
    """
    fitted = {10: _FixedBooster(0.0), 90: _FixedBooster(10.0)}

    # 12% outside, comfortably inside a 20% budget → no widening.
    assert _conformal_factor(fitted, _calib([5.0] * 88 + [1000.0] * 12)) == 0.0

    # 20% outside, exactly at the budget → the (n+1) correction still bites.
    at_budget = _conformal_factor(fitted, _calib([5.0] * 80 + [1000.0] * 20))
    assert at_budget > 0.0

    # More of the tail outside cannot make the band narrower.
    beyond = _conformal_factor(fitted, _calib([5.0] * 60 + [1000.0] * 40))
    assert beyond >= at_budget


def test_alpha_matches_the_band_the_frontend_draws() -> None:
    """q10-q90 is a nominal 80% interval; alpha is its miscoverage."""
    assert CONFORMAL_ALPHA == pytest.approx(0.20)


# ─── The split ───────────────────────────────────────────────────────


def test_the_split_is_disjoint_reproducible_and_trains_on_the_past() -> None:
    frame = pd.DataFrame(
        {"y": range(1000), "time_utc": pd.date_range("2025-01-01", periods=1000, freq="h")}
    )
    train, calib, test = _split(frame)

    assert len(train) + len(calib) + len(test) == len(frame)
    ids = [set(part.index) for part in (train, calib, test)]
    assert not (ids[0] & ids[1]) and not (ids[0] & ids[2]) and not (ids[1] & ids[2])

    # Training is strictly the earliest rows: no future hour informs the fit.
    assert max(train.index) < min(min(calib.index), min(test.index))

    # Calibration and test are drawn from the tail at random, so they
    # interleave in time — that is what makes them exchangeable with each
    # other, which is what conformal calibration requires.
    assert min(calib.index) != min(test.index)
    assert _split(frame)[1].index.equals(calib.index), "split must be reproducible"


# ─── Serving applies exactly what the trainer measured ───────────────


def test_serving_widens_the_band_by_the_stored_factor() -> None:
    raw_lo, raw_hi, factor = 4.0, 10.0, 0.25
    pad = factor * (raw_hi - raw_lo)
    lo, _mid, hi = sorted([max(0.0, raw_lo - pad), 7.0, max(0.0, raw_hi + pad)])
    assert (lo, hi) == (2.5, 11.5)
    assert hi - lo == pytest.approx((raw_hi - raw_lo) * (1 + 2 * factor))


def test_a_missing_calibration_artifact_serves_the_raw_band() -> None:
    """An older artifact set has no conformal.json. That must degrade to "no
    widening", not to a crash, so a checkout mid-upgrade still serves."""
    aq_infer._load_conformal.cache_clear()
    original = aq_infer.ART
    try:
        aq_infer.ART = REPO_ROOT / "data" / "models" / "does-not-exist"
        assert aq_infer._load_conformal() == {}
    finally:
        aq_infer.ART = original
        aq_infer._load_conformal.cache_clear()


# ─── The shipped artifact ────────────────────────────────────────────


def _require_artifact() -> dict:
    path = ART / "conformal.json"
    if not path.exists():
        pytest.skip("model not trained on this checkout — run `make train-aq`")
    return json.loads(path.read_text())


def test_the_shipped_factors_cover_every_horizon_and_never_narrow() -> None:
    payload = _require_artifact()
    factors = payload["factors"]
    assert {int(k.lstrip("h")) for k in factors} == set(aq_infer.HORIZONS_H)
    assert all(v >= 0 for v in factors.values()), "a factor must never narrow the band"
    assert payload["nominal_coverage"] == pytest.approx(0.80)


def test_the_shipped_band_measures_close_to_its_nominal_coverage() -> None:
    """The whole point of the calibration. Uncalibrated this model covered
    57-66% while claiming 80%; a regression back to that is a correctness bug,
    not a cosmetic one."""
    metrics = (
        json.loads((ART / "metrics.json").read_text()) if (ART / "metrics.json").exists() else None
    )
    if not metrics:
        pytest.skip("metrics not built")

    for horizon, m in metrics.items():
        if "band_coverage_calibrated" not in m:
            pytest.skip("metrics predate calibration — retrain")
        covered = m["band_coverage_calibrated"]
        assert 0.74 <= covered <= 0.88, f"{horizon} covers {covered:.1%}, nominal is 80%"
        assert covered > m["band_coverage_raw"], f"{horizon} calibration did not widen"


def test_serving_reports_the_band_it_actually_draws() -> None:
    payload = aq_infer.predict_forecast()
    if payload is None:
        pytest.skip("model or archive not present")

    band = payload["band"]
    assert band["calibrated"] is True
    assert band["nominal_coverage"] == pytest.approx(0.80)
    assert 0.74 <= band["measured_coverage"] <= 0.88

    for point in payload["forecasts"]:
        assert point["q10"] <= point["q50"] <= point["q90"]
        assert point["q10"] >= 0.0, "PM2.5 cannot be negative"
