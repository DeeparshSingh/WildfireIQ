"""Data-quality invariants. Catches regressions where an upstream feed
or a parser silently shifts shape and corrupts every downstream chart.

Skipped (not failed) when the relevant parquet is absent — so a fresh
clone passes the suite before bootstrapping.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED = REPO_ROOT / "data" / "processed"


def _load(name: str) -> pd.DataFrame:
    p = PROCESSED / name
    if not p.exists():
        pytest.skip(f"{name} not built — run `make bootstrap` first")
    return pd.read_parquet(p)


# ─── Fires ─────────────────────────────────────────────────────────────


def test_fires_historical_in_canada() -> None:
    df = _load("fires_historical.parquet")
    df = df.dropna(subset=["latitude", "longitude"])
    in_bc_ish = (
        df.latitude.between(48.0, 60.5) & df.longitude.between(-140.5, -114.0)
    )
    bad = (~in_bc_ish).sum()
    assert bad / len(df) < 0.005, f"{bad} fires outside BC bounding box (> 0.5%)"


def test_fires_historical_year_range() -> None:
    df = _load("fires_historical.parquet")
    assert df.fire_year.min() >= 1950
    assert df.fire_year.max() <= 2030


def test_fires_historical_hectares_positive() -> None:
    df = _load("fires_historical.parquet")
    h = df.hectares.dropna()
    assert (h >= 0).all(), "negative hectares present"
    # 99th percentile sanity ceiling — single fires above 500 k ha are
    # rare but real (2017 Elephant Hill ≈ 192 k).
    assert h.quantile(0.99) < 1_000_000


# ─── Weather archive ───────────────────────────────────────────────────


def test_weather_archive_long_enough() -> None:
    df = _load("weather_kamloops_archive_daily.parquet")
    assert len(df) >= 9_000, f"weather archive has {len(df)} rows; expected ≥ 9000"


def test_weather_temp_in_realistic_range() -> None:
    df = _load("weather_kamloops_archive_daily.parquet")
    t = df.temp_max_c.dropna()
    # Kamloops historical extremes: ~46 °C (2021 dome), ~−35 °C
    assert t.min() > -45
    assert t.max() < 50


def test_weather_precip_non_negative() -> None:
    df = _load("weather_kamloops_archive_daily.parquet")
    p = df.precip_mm.dropna()
    assert (p >= 0).all()


# ─── Air quality ───────────────────────────────────────────────────────


def test_aqhi_realtime_within_band() -> None:
    df = _load("aqhi_kamloops_recent.parquet")
    if "aqhi" not in df.columns:
        pytest.skip("aqhi column not present")
    a = df.aqhi.dropna()
    if len(a) == 0:
        pytest.skip("no AQHI rows")
    # Health Canada AQHI is reported as 1-10 with "10+" capped at ~12 in raw form.
    assert a.min() >= 1
    assert a.max() <= 12, f"AQHI value {a.max()} exceeds 12 cap"


def test_aq_hourly_pm25_non_negative() -> None:
    df = _load("aq_hourly_kamloops.parquet")
    p = df.pm2_5.dropna()
    assert (p >= 0).all()
    # PM2.5 above 1000 µg/m³ is implausible even during the worst smoke events.
    assert p.max() < 1000


# ─── Seasonal metrics (Phase 6) ────────────────────────────────────────


def test_seasonal_metrics_years_contiguous() -> None:
    df = _load("seasonal_metrics.parquet")
    yrs = df.year.tolist()
    gaps = [b - a for a, b in zip(yrs, yrs[1:])]
    assert all(g == 1 for g in gaps), f"non-contiguous year set: gaps {gaps}"


def test_seasonal_metrics_no_nulls_in_core_fields() -> None:
    df = _load("seasonal_metrics.parquet")
    core = ["mean_jul_temp_c", "julaug_precip_mm", "max_julaug_fwi", "days_fwi_ge_19"]
    for c in core:
        assert df[c].notna().all(), f"{c} has nulls"


def test_seasonal_metrics_fwi_days_within_year() -> None:
    df = _load("seasonal_metrics.parquet")
    assert (df.days_fwi_ge_19 <= 366).all()
    assert (df.days_fwi_ge_19 >= 0).all()


# ─── Evac ──────────────────────────────────────────────────────────────


def test_evac_active_status_vocabulary() -> None:
    df = _load("evac_active.parquet")
    if len(df) == 0:
        pytest.skip("no active evac rows right now")
    if "status" not in df.columns:
        pytest.skip("no status column")
    statuses = set(df.status.dropna().str.lower().str.strip())
    # The BCEM ORDER_ALERT_STATUS field uses these three terms.
    allowed = {"order", "alert", "rescind", "advisory"}
    unknown = statuses - allowed
    assert not unknown, f"unknown evac statuses: {unknown}"
