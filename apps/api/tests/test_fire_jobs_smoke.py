"""Smoke test: instantiate fire ingest jobs and run the current-fires job.

These call the real upstream feeds, so they are marked `live` and left out of
the default run — `make test` must pass on a plane. Run them with
`make test-live` when you want to know whether the sources are still answering.
"""

import asyncio

import pytest
from sqlalchemy import text

from wildfireiq_api.db import get_engine
from wildfireiq_api.ingest.base import run_job
from wildfireiq_api.ingest.databc_fires_current import DataBCFiresCurrentJob
from wildfireiq_api.ingest.databc_fires_historical import DataBCFiresHistoricalJob
from wildfireiq_api.ingest.firms_hotspots import FIRMSHotspotsJob


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


@pytest.mark.live
async def test_current_fires_job_runs_against_databc() -> None:
    await _init_db()

    # Instantiate all three (verify imports / class definition).
    _ = FIRMSHotspotsJob()
    _ = DataBCFiresHistoricalJob()

    rpt = await run_job(DataBCFiresCurrentJob())
    print(rpt)
    # This used to only print. A failed ingest passed silently, which defeats
    # the point of a smoke test.
    assert rpt.status == "ok", f"DataBC current-fires ingest failed: {rpt.error}"
    assert rpt.rows_written and rpt.rows_written > 0, "DataBC returned no fires"


if __name__ == "__main__":
    asyncio.run(test_current_fires_job_runs_against_databc())
