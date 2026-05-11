"""Smoke test: instantiate fire ingest jobs and run the current-fires job."""

import asyncio

from wildfireiq_api.db import get_engine
from wildfireiq_api.ingest.base import run_job
from wildfireiq_api.ingest.databc_fires_current import DataBCFiresCurrentJob
from wildfireiq_api.ingest.databc_fires_historical import DataBCFiresHistoricalJob
from wildfireiq_api.ingest.firms_hotspots import FIRMSHotspotsJob
from sqlalchemy import text


async def _init_db() -> None:
    """Ensure ingest_runs table exists for the smoke test."""
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

    # Instantiate all three (verify imports / class definition).
    _ = FIRMSHotspotsJob()
    _ = DataBCFiresHistoricalJob()

    # Smoke-run the live current fires job.
    rpt = await run_job(DataBCFiresCurrentJob())
    print(rpt)


if __name__ == "__main__":
    asyncio.run(test())
