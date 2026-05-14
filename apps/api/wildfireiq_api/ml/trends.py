"""Robust trend estimation utilities for Phase 6 climate charts.

`theil_sen_with_ci` computes the Theil-Sen median slope of `y ~ x` plus a
bootstrap-derived 95% confidence interval. Theil-Sen is the canonical
robust slope estimator used by PCIC and climate researchers when the
residuals aren't Gaussian — outliers (wildfire seasons, eruptions, weird
years) can't drag the slope around the way an OLS line does.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class TrendResult:
    slope: float  # units of y per unit of x (typically per year)
    intercept: float
    slope_ci_lo: float  # 95% bootstrap CI
    slope_ci_hi: float
    n: int

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self.slope * x + self.intercept


def theil_sen_with_ci(
    x: np.ndarray,
    y: np.ndarray,
    *,
    n_boot: int = 1000,
    rng_seed: int = 42,
) -> TrendResult:
    """Theil-Sen slope + bootstrap CI. Drops NaN pairs."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]
    n = len(x)
    if n < 3:
        return TrendResult(slope=float("nan"), intercept=float("nan"),
                           slope_ci_lo=float("nan"), slope_ci_hi=float("nan"), n=n)

    slope = _theil_sen_slope(x, y)
    intercept = float(np.median(y - slope * x))

    rng = np.random.default_rng(rng_seed)
    boots = np.empty(n_boot)
    idx_range = np.arange(n)
    for i in range(n_boot):
        idx = rng.choice(idx_range, size=n, replace=True)
        boots[i] = _theil_sen_slope(x[idx], y[idx])
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])

    return TrendResult(
        slope=float(slope),
        intercept=intercept,
        slope_ci_lo=float(lo),
        slope_ci_hi=float(hi),
        n=n,
    )


def _theil_sen_slope(x: np.ndarray, y: np.ndarray) -> float:
    """Median of pairwise slopes. O(n²) is fine for ≤ 100 years."""
    n = len(x)
    if n < 2:
        return float("nan")
    # All unique pairs
    i, j = np.triu_indices(n, k=1)
    dx = x[j] - x[i]
    dy = y[j] - y[i]
    valid = dx != 0
    if not valid.any():
        return float("nan")
    slopes = dy[valid] / dx[valid]
    return float(np.median(slopes))
