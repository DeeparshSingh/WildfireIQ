"""Smoke test: live-fetch OpenMeteoKamloopsJob and CWFISFWIDailyJob."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from wildfireiq_api.ingest.base import run_job
from wildfireiq_api.ingest.cwfis_fwi import CWFISFWIDailyJob
from wildfireiq_api.ingest.open_meteo import OpenMeteoKamloopsJob
from wildfireiq_api.paths import PROCESSED_ROOT


async def _main() -> int:
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
            CWFISFWIDailyJob(),
            ["fwi_stations_today.parquet"],
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

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        return 1
    print("\nALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
