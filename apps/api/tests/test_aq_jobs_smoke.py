"""Smoke test: AQ + smoke + evac + climate projection jobs (live, cheap).

These call the real upstream feeds, so they are marked `live` and left out of
the default run — `make test` must pass on a plane. Run them with
`make test-live` when you want to know whether the sources are still answering.
"""

import asyncio

import pytest
from sqlalchemy import text

from wildfireiq_api.db import get_engine
from wildfireiq_api.ingest.base import run_job
from wildfireiq_api.ingest.bcem_evac import BCEMEvacuationJob
from wildfireiq_api.ingest.climatedata_projections import ClimateDataProjectionsJob
from wildfireiq_api.ingest.firework_smoke import FireWorkSmokeForecastJob
from wildfireiq_api.ingest.geomet_aqhi import GeoMetAQHIRealtimeJob
from wildfireiq_api.ingest.waqi import WAQIKamloopsJob
from wildfireiq_api.settings import get_settings


async def _init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS ingest_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_name TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    rows_in INTEGER,
                    rows_written INTEGER,
                    bytes_written INTEGER,
                    duration_ms INTEGER,
                    note TEXT,
                    error TEXT
                )
                """
            )
        )


@pytest.mark.live
async def test_air_quality_and_evac_jobs_run_against_their_sources() -> None:
    await _init_db()

    failures: list[str] = []

    for job, timeout in (
        (GeoMetAQHIRealtimeJob(), None),
        (FireWorkSmokeForecastJob(), 120.0),
        (ClimateDataProjectionsJob(), None),
    ):
        rpt = await run_job(job) if timeout is None else await run_job(job, timeout=timeout)
        print(f"--- {job.name} --- {rpt}")
        if rpt.status != "ok":
            failures.append(f"{job.name}: {rpt.error}")

    if get_settings().waqi_token:
        rpt = await run_job(WAQIKamloopsJob())
        print(f"--- waqi_kamloops --- {rpt}")
        if rpt.status != "ok":
            failures.append(f"waqi_kamloops: {rpt.error}")
    else:
        print("--- waqi_kamloops SKIPPED (no token) ---")

    # BCEM publishes through several ArcGIS endpoints and tolerates some of
    # them being down, so "partial" is a pass here where it would not be
    # for the others.
    rpt = await run_job(BCEMEvacuationJob())
    print(f"--- bcem_evac --- {rpt}")
    if rpt.status not in ("ok", "partial"):
        failures.append(f"bcem_evac: {rpt.error}")

    assert not failures, "live ingest failures:\n  " + "\n  ".join(failures)


if __name__ == "__main__":
    asyncio.run(test_air_quality_and_evac_jobs_run_against_their_sources())
