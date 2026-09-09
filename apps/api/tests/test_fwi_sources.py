"""Regression tests for the two Fire Weather Index ingest jobs.

Both of the bugs pinned here were silent. `cwfis_fwi_daily` reported "GeoServer
unreachable" for the entire build while the host was up and only the layer name
had changed, and `derived_fwi_stations` fed the Van Wagner port a 30-day window,
which is far too short for the Drought Code to spin up and produced values
roughly a third of NRCan's at the same stations. Neither showed up as an
exception; both needed someone to compare numbers against ground truth.

These tests are offline. The live check lives in test_weather_jobs_smoke.py.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import mkdtemp
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from wildfireiq_api.ingest import cwfis_fwi, derived_fwi
from wildfireiq_api.ingest.cwfis_fwi import _PARAMS, CWFISFWIDailyJob, _in_bbox
from wildfireiq_api.ingest.derived_fwi import DerivedFWIStationsJob
from wildfireiq_api.ml.fwi import compute_fwi

# ── cwfis_fwi_daily ─────────────────────────────────────────────────────────


def test_cwfis_requests_the_layer_that_actually_exists() -> None:
    """NRCan renamed fwi_stns_current -> firewx_stns_current."""
    assert _PARAMS["typeName"] == "public:firewx_stns_current"


def test_cwfis_sends_no_server_side_bbox() -> None:
    """WFS 2.0 reads EPSG:4326 as lat,lon and honoured CRS84 only loosely here.

    Both returned stations outside British Columbia, so filtering is done on
    the features' own lat/lon instead.
    """
    assert "bbox" not in _PARAMS


def test_bbox_filter_rejects_the_stations_that_leaked_through() -> None:
    # Real coordinates from the bad server-side bbox: a Saskatchewan station
    # and a latitude well north of the province.
    assert not _in_bbox(49.633, -109.517)
    assert not _in_bbox(64.12, -120.0)
    assert _in_bbox(50.6745, -120.3273)  # Kamloops


def test_the_two_fwi_jobs_do_not_write_the_same_file() -> None:
    """They both wrote fwi_stations_today.parquet, so whichever ran last won."""
    assert cwfis_fwi.OUTPUT_NAME != derived_fwi.OUTPUT_NAME
    assert derived_fwi.OUTPUT_NAME == "fwi_stations_today.parquet", "/api/fwi/today reads this name"


def test_cwfis_cadence_runs_after_bc_stations_report() -> None:
    """Noon-LST observations: BC noon is 20:00 UTC.

    The job used to run at 18:00 UTC, which is before any BC station has
    reported, so it pulled a valid feed of eastern stations and filtered every
    one of them out.
    """
    hour = int(CWFISFWIDailyJob.cadence.split()[1])
    assert hour >= 21, f"{hour}:00 UTC is too early for BC noon-LST observations"


async def test_cwfis_keeps_the_previous_file_when_no_bc_station_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty result must not overwrite real readings.

    `firewx_stns_current` carries only stations that have already reported, so
    a run made too early legitimately contains no BC row. Writing that out
    would throw away the cross-check for nothing.
    """
    eastern_only = {
        "features": [
            {
                "properties": {"lat": 47.31, "lon": -53.99, "name": "ARGENTIA", "fwi": 0.0},
                "geometry": None,
            }
        ]
    }

    class _Resp:
        status_code = 200

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return eastern_only

    class _Client:
        async def get(self, url: str, params: dict, timeout: float):
            return _Resp()

    job = CWFISFWIDailyJob()
    ctx = SimpleNamespace(
        client=_Client(),
        log=SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None),
        started_at_utc=datetime(2026, 9, 9, 18, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(job, "raw_path", lambda name: Path(mkdtemp()) / name)

    report = await job.run(ctx)  # type: ignore[arg-type]

    assert report.status == "partial", "an empty BC result is not a success"
    assert report.rows_written == 0
    assert report.note and "none inside British Columbia" in report.note


# ── derived_fwi_stations ────────────────────────────────────────────────────


class _CapturingClient:
    """Records the query params, returns one usable day of weather."""

    def __init__(self) -> None:
        self.params: dict[str, str] = {}

    async def get(self, url: str, params: dict[str, str]):
        self.url = url
        self.params = params

        class _R:
            status_code = 200

            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict:
                return {
                    "daily": {
                        "time": ["2026-09-08"],
                        "temperature_2m_max": [28.0],
                        "temperature_2m_min": [12.0],
                        "relative_humidity_2m_min": [20.0],
                        "wind_speed_10m_max": [14.0],
                        "precipitation_sum": [0.0],
                        "vapour_pressure_deficit_max": [2.5],
                        "et0_fao_evapotranspiration": [5.0],
                    }
                }

        return _R()


async def test_derived_fwi_pulls_from_the_season_start_not_a_rolling_window() -> None:
    client = _CapturingClient()
    await derived_fwi._pull_station_weather(
        client, "Kamloops", 50.6745, -120.3273, today=date(2026, 9, 8)
    )
    assert client.params["start_date"] == "2026-04-01", (
        "the Drought Code accumulates all season; a short window starts it at 15"
    )
    assert client.params["end_date"] == "2026-09-08"
    assert "past_days" not in client.params
    assert client.url == derived_fwi.OPEN_METEO_ARCHIVE


async def test_derived_fwi_before_april_falls_back_to_last_season() -> None:
    client = _CapturingClient()
    await derived_fwi._pull_station_weather(
        client, "Kamloops", 50.6745, -120.3273, today=date(2026, 2, 15)
    )
    assert client.params["start_date"] == "2025-04-01"


def test_derived_fwi_cadence_matches_a_daily_index() -> None:
    """It ran every 30 minutes, re-deriving an unchanged daily number 48x a day."""
    assert DerivedFWIStationsJob.cadence == "0 */6 * * *"


# ── the property that made the bug visible ──────────────────────────────────


def test_drought_code_keeps_climbing_through_a_dry_season() -> None:
    """DC has a ~52-day time constant, so the window length dominates it.

    A 30-day window cannot reach the values a full season produces. This is
    the arithmetic that made the shipped figures a third of NRCan's.
    """
    days = pd.date_range("2026-04-01", "2026-09-08", freq="D")
    dry = pd.DataFrame(
        {
            "day_local": days,
            "temp_max_c": 28.0,
            "rh_min_pct": 20.0,
            "wind_max_kmh": 12.0,
            "precip_mm": 0.0,
        }
    )
    full = compute_fwi(dry)
    last30 = compute_fwi(dry.tail(30).reset_index(drop=True))

    dc_full = float(full["dc"].iloc[-1])
    dc_short = float(last30["dc"].iloc[-1])

    assert dc_full > dc_short * 2, (
        f"season spin-up {dc_full:.0f} should dwarf a 30-day window {dc_short:.0f}"
    )
    # Monotone under zero precipitation.
    assert np.all(np.diff(full["dc"].to_numpy()) >= -1e-9)


def test_one_season_of_history_is_enough_and_thirty_days_is_not() -> None:
    """Why the job starts at 1 April rather than pulling more, or less.

    compute_fwi resets the carryover codes each calendar year, so history
    before the current 1 April cannot reach the answer: starting a year or two
    earlier lands within half a percent. A 30-day window, by contrast, is off
    by a factor of five.
    """

    def dc_from(start: str) -> float:
        days = pd.date_range(start, "2026-09-08", freq="D")
        dry = pd.DataFrame(
            {
                "day_local": days,
                "temp_max_c": 28.0,
                "rh_min_pct": 20.0,
                "wind_max_kmh": 12.0,
                "precip_mm": 0.0,
            }
        )
        return float(compute_fwi(dry)["dc"].iloc[-1])

    season = dc_from("2026-04-01")
    two_seasons = dc_from("2025-04-01")
    short_window = dc_from("2026-08-09")

    assert abs(season - two_seasons) / two_seasons < 0.01, (
        "the yearly reset should make earlier history irrelevant"
    )
    assert short_window < season / 3, (
        f"30 days reaches only {short_window:.0f} against {season:.0f} for a season"
    )
