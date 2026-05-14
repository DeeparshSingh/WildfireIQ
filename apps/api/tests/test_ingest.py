"""Parser + schema validation for the ingest pipeline (Phase 1 spec).

These tests don't hit the network. They validate:

  • Every processed parquet that exists on disk conforms to the column
    contract the rest of the codebase relies on (the router accessors,
    the ML trainers, the climate trends).
  • The non-trivial parsers (smoke ISO-8601 expansion, FWI Van Wagner
    port, fires-unified union, seasonal metrics builder) produce the
    expected shape on synthetic input.

The earlier smoke tests in `test_*_jobs_smoke.py` do hit the network — we
keep those for an end-to-end check and leave this file for fast,
hermetic unit coverage.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED = REPO_ROOT / "data" / "processed"


# ─── Parquet schema contracts ─────────────────────────────────────────


EXPECTED_COLUMNS: dict[str, set[str]] = {
    "fires_historical.parquet": {
        "fire_id", "fire_year", "fire_name", "hectares",
        "discovery_date_utc", "ignition_cause", "latitude", "longitude",
        "geom_wkt", "geom_kind",
    },
    "fires_current.parquet": {
        "fire_id", "fire_name", "status", "stage_of_control", "hectares",
        "discovery_date_utc", "latitude", "longitude", "geom_wkt",
        "geom_kind", "fetched_at_utc",
    },
    "firms_hotspots_recent.parquet": {
        "latitude", "longitude", "acq_datetime_utc",
    },
    "weather_kamloops_archive_daily.parquet": {
        "day_local", "temp_max_c", "temp_min_c", "precip_mm",
    },
    "aq_hourly_kamloops.parquet": {
        "time_utc", "pm2_5",
    },
    "evac_active.parquet": {
        "event_id", "status", "issuing_agency",
    },
    "fwi_stations_today.parquet": {
        "station_id", "latitude", "longitude", "fwi",
    },
}


@pytest.mark.parametrize("filename,required", list(EXPECTED_COLUMNS.items()))
def test_processed_parquet_schema(filename: str, required: set[str]) -> None:
    """Every processed parquet must carry the columns the consumers expect."""
    p = PROCESSED / filename
    if not p.exists():
        pytest.skip(f"{filename} not yet built — run `make bootstrap` first")
    df = pd.read_parquet(p)
    missing = required - set(df.columns)
    assert not missing, f"{filename} missing columns: {missing}"
    assert len(df) > 0, f"{filename} is empty"


# ─── Smoke ISO-8601 interval expander ─────────────────────────────────


def test_smoke_duration_parser_period_units() -> None:
    """The smoke ingest reads WMS time intervals of the form
    `start/end/PT1H` and expands them into hourly timesteps. Verify the
    duration parser handles the units we actually see in production."""
    from wildfireiq_api.ingest.firework_smoke import _parse_iso8601_duration

    assert _parse_iso8601_duration("PT1H") == timedelta(hours=1)
    assert _parse_iso8601_duration("PT30M") == timedelta(minutes=30)
    assert _parse_iso8601_duration("PT3H") == timedelta(hours=3)
    assert _parse_iso8601_duration("P1D") == timedelta(days=1)
    assert _parse_iso8601_duration("garbage") is None


# ─── Van Wagner FWI port — algebraic sanity ───────────────────────────


def test_fwi_port_runs_on_synthetic_year() -> None:
    """Feed the Van Wagner port a synthetic year of hot-dry weather and
    verify it produces non-negative FWI values in a plausible range."""
    from wildfireiq_api.ml.fwi import compute_fwi

    days = pd.date_range("2020-04-01", "2020-09-30", freq="D")
    df = pd.DataFrame({
        "day_local": days,
        "temp_max_c": 30.0,
        "rh_min_pct": 25.0,
        "wind_max_kmh": 15.0,
        "precip_mm": 0.0,
    })
    out = compute_fwi(df)
    assert (out["fwi"] >= 0).all()
    assert out["fwi"].max() < 200  # sanity ceiling
    # Under sustained hot-dry conditions FWI should grow into the
    # "high" range (≥ 5) within the first month.
    assert out["fwi"].iloc[30] >= 5


# ─── fires_unified union ──────────────────────────────────────────────


def test_fires_unified_columns() -> None:
    """If the unified parquet has been built, validate its contract."""
    p = PROCESSED / "fires_unified.parquet"
    if not p.exists():
        pytest.skip("fires_unified.parquet not yet built — run `make fires-unified`")
    df = pd.read_parquet(p)
    required = {"fire_id", "fire_year", "hectares", "discovery_date_utc",
                "latitude", "longitude", "source"}
    assert required.issubset(df.columns)
    assert set(df["source"].unique()).issubset({"historical", "current"})
    assert len(df) >= 10_000  # we should never silently drop most rows


# ─── seasonal_metrics builder ──────────────────────────────────────────


def test_seasonal_metrics_columns() -> None:
    p = PROCESSED / "seasonal_metrics.parquet"
    if not p.exists():
        pytest.skip("seasonal_metrics.parquet not yet built — run `make seasonal-metrics`")
    df = pd.read_parquet(p)
    required = {"year", "area_burned_ha", "mean_jul_temp_c",
                "julaug_precip_mm", "mean_julaug_vpd_kpa",
                "max_julaug_fwi", "days_fwi_ge_19",
                "season_start_doy", "season_end_doy", "season_length_days"}
    assert required.issubset(df.columns)
    # Sanity: years are unique and monotonically sorted ascending.
    assert df["year"].is_unique
    assert (df["year"].diff().dropna() > 0).all()
    # Sanity: FWI extreme-day count is non-negative.
    assert (df["days_fwi_ge_19"] >= 0).all()


# ─── trends helper — Theil-Sen + bootstrap CI ─────────────────────────


def test_theil_sen_recovers_known_slope() -> None:
    """Feed the estimator a perfect linear series and verify it
    recovers the slope to within tolerance, with a tight CI."""
    import numpy as np
    from wildfireiq_api.ml.trends import theil_sen_with_ci

    rng = np.random.default_rng(0)
    x = np.arange(30, dtype=float)
    y = 1.5 * x + 4.0 + rng.normal(0, 0.1, size=30)
    t = theil_sen_with_ci(x, y, n_boot=200)
    assert abs(t.slope - 1.5) < 0.05
    assert t.slope_ci_lo < 1.5 < t.slope_ci_hi
    assert t.n == 30


def test_theil_sen_handles_nan() -> None:
    """NaN rows must be dropped pairwise, not poison the slope."""
    import numpy as np
    from wildfireiq_api.ml.trends import theil_sen_with_ci

    x = np.array([0, 1, 2, 3, 4, 5], dtype=float)
    y = np.array([0, 2, np.nan, 6, 8, np.nan], dtype=float)
    t = theil_sen_with_ci(x, y, n_boot=200)
    assert abs(t.slope - 2.0) < 0.001
    assert t.n == 4
