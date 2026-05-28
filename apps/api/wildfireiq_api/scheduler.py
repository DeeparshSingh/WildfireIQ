"""APScheduler wrapper that runs every recurring ingest job on its cadence."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from .db import session_scope
from .ingest.base import IngestJob, run_job
from .ingest.registry import scheduled_jobs

log = structlog.get_logger()
_scheduler: AsyncIOScheduler | None = None


def _wrap(job: IngestJob):
    async def runner():
        try:
            await run_job(job)
        except Exception as exc:
            log.error("scheduler.job.crash", job=job.name, error=str(exc))

    return runner


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone="UTC")
    for job in scheduled_jobs():
        cadence = job.cadence
        assert cadence is not None
        trig = CronTrigger.from_crontab(cadence, timezone="UTC")
        _scheduler.add_job(
            _wrap(job),
            trigger=trig,
            id=job.name,
            name=job.label or job.name,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
        log.info("scheduler.registered", job=job.name, cadence=cadence)

    _scheduler.start()
    log.info("scheduler.started", jobs=len(_scheduler.get_jobs()))
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("scheduler.stopped")


async def refresh_stale_jobs(max_age_minutes: int) -> None:
    """Run every recurring job whose latest successful run is older than the
    threshold. Called at uvicorn startup so cold-start = fresh data even when
    APScheduler hasn't yet fired its first tick of the day.

    Runs jobs concurrently to keep startup fast. Errors are logged, never
    raised — a failed upstream shouldn't block the API from booting.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=max_age_minutes)
    cutoff_iso = cutoff.isoformat()

    to_run: list[IngestJob] = []
    async with session_scope() as session:
        for job in scheduled_jobs():
            result = await session.execute(
                text(
                    "SELECT started_at FROM ingest_runs "
                    "WHERE job_name = :n AND status = 'ok' "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"n": job.name},
            )
            row = result.first()
            last_iso = row[0] if row else None
            if last_iso is None or last_iso < cutoff_iso:
                to_run.append(job)

    if not to_run:
        log.info("startup_refresh.nothing_to_run")
        return

    log.info(
        "startup_refresh.running",
        count=len(to_run),
        jobs=[j.name for j in to_run],
    )

    async def _safe(j: IngestJob):
        try:
            await run_job(j)
        except Exception as exc:
            log.warning("startup_refresh.job_failed", job=j.name, error=str(exc))

    # Cap parallelism at 5 so we don't hammer a single upstream.
    sem = asyncio.Semaphore(5)

    async def _gated(j: IngestJob):
        async with sem:
            await _safe(j)

    await asyncio.gather(*[_gated(j) for j in to_run])
    log.info("startup_refresh.complete")


async def run_now(name: str) -> None:
    """Fire a specific job immediately, outside its cron schedule. Useful from /api/admin or tests."""
    from .ingest.registry import all_jobs

    jobs = all_jobs()
    if name not in jobs:
        raise ValueError(f"Unknown job: {name!r}. Known: {sorted(jobs)}")
    await run_job(jobs[name])


# CLI entry: `uv run python -m wildfireiq_api.scheduler run <name>`
def _main() -> None:
    import sys

    if len(sys.argv) < 3 or sys.argv[1] != "run":
        print("Usage: python -m wildfireiq_api.scheduler run <job_name>", file=sys.stderr)
        sys.exit(2)
    asyncio.run(run_now(sys.argv[2]))


if __name__ == "__main__":
    _main()
