"""Smoke test: live-fetch OpenMeteoKamloopsJob and CWFISFWIDailyJob.

These call the real upstream feeds, so they are marked `live` and left out of
the default run — `make test` must pass on a plane. Run them with
`make test-live` when you want to know whether the sources are still answering.

This file was named `test_*` but its entry point was `_main`, so pytest
collected nothing from it: it looked covered for the whole build and never ran.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from wildfireiq_api.ingest.base import run_job
from wildfireiq_api.ingest.cwfis_fwi import CWFISFWIDailyJob
from wildfireiq_api.ingest.open_meteo import OpenMeteoKamloopsJob
from wildfireiq_api.paths import PROCESSED_ROOT


@pytest.mark.live
async def test_weather_and_cwfis_jobs_run_against_their_sources() -> None:
    failures: list[str] = []

    for job, expected in (
        (
            OpenMeteoKamloopsJob(),
            [
                "weather_kamloops_current.parquet",
                "weather_kamloops_hourly.parquet",
                "weather_kamloops_daily.parquet",
            ],
        ),
        (
            # Its own file — fwi_stations_today.parquet belongs to
            # derived_fwi_stations, which rewrites it every six hours.
            CWFISFWIDailyJob(),
            ["fwi_stations_cwfis.parquet"],
        ),
    ):
        print(f"\n=== Running {job.name} ===")
        report = await run_job(job)
        print(
            f"status={report.status} rows_in={report.rows_in} "
            f"rows_written={report.rows_written} duration_ms={report.duration_ms} "
            f"error={report.error}"
        )
        if report.status != "ok":
            failures.append(f"{job.name}: status={report.status} error={report.error}")
            continue
        for fname in expected:
            p: Path = PROCESSED_ROOT / fname
            if not p.exists():
                failures.append(f"{job.name}: missing {p}")
            else:
                print(f"  ok  {p} ({p.stat().st_size} bytes)")

    assert not failures, "live ingest failures:\n  " + "\n  ".join(failures)


if __name__ == "__main__":
    try:
        asyncio.run(test_weather_and_cwfis_jobs_run_against_their_sources())
    except AssertionError as exc:
        print(exc)
        sys.exit(1)
    print("\nALL OK")
