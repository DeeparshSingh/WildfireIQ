"""Smoke test: AQ + smoke + evac + climate projection jobs (live, cheap)."""

import asyncio

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


async def test() -> None:
    await _init_db()

    print("--- GeoMetAQHIRealtimeJob ---")
    print(await run_job(GeoMetAQHIRealtimeJob()))

    print("--- FireWorkSmokeForecastJob ---")
    print(await run_job(FireWorkSmokeForecastJob(), timeout=120.0))

    print("--- ClimateDataProjectionsJob ---")
    print(await run_job(ClimateDataProjectionsJob()))

    if get_settings().waqi_token:
        print("--- WAQIKamloopsJob ---")
        print(await run_job(WAQIKamloopsJob()))
    else:
        print("--- WAQIKamloopsJob SKIPPED (no token) ---")

    print("--- BCEMEvacuationJob ---")
    rpt = await run_job(BCEMEvacuationJob())
    print(rpt)
    if rpt.status == "partial":
        print("(BCEM endpoints unreachable — acceptable per spec)")


if __name__ == "__main__":
    asyncio.run(test())
