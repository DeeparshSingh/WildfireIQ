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
from .ingest.registry import dependency_waves, scheduled_jobs, with_dependents

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


#: Startup catch-up parallelism. Five keeps a cold start quick without
#: hammering any single upstream (most of them are Open-Meteo or DataBC).
_REFRESH_CONCURRENCY = 5


async def _stale_jobs(max_age_minutes: int) -> list[IngestJob]:
    """Recurring jobs whose latest successful run is older than the threshold."""
    cutoff_iso = (datetime.now(UTC) - timedelta(minutes=max_age_minutes)).isoformat()

    stale: list[IngestJob] = []
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
                stale.append(job)
    return stale


async def refresh_stale_jobs(max_age_minutes: int) -> None:
    """Bring stale data up to date at uvicorn startup, in dependency order.

    Cold start, or a laptop that has been closed for a week, leaves the
    processed parquets behind. APScheduler will not fire until its next tick,
    so this catches up immediately.

    Two things matter beyond "what is stale".

    Ordering: `derived_risk_features` reads the region weather archives, and
    `derived_seasonal_metrics` reads the Kamloops archive. The nightly cron
    times are staggered to respect that, but a catch-up run has no clock to
    lean on, so jobs are grouped into dependency waves and each wave finishes
    before the next begins. Within a wave, jobs run in parallel.

    Completeness: a derived job can be fresh by the clock while the inputs it
    reads are rebuilt in this same pass, which would leave its output older
    than its sources. So the stale set is widened to include everything
    downstream of it before the waves are built.

    Errors are logged, never raised: a dead upstream must not stop the API
    from booting.
    """
    stale = await _stale_jobs(max_age_minutes)
    if not stale:
        log.info("startup_refresh.nothing_to_run")
        return

    to_run = with_dependents(stale)
    waves = dependency_waves(to_run)
    log.info(
        "startup_refresh.running",
        count=len(to_run),
        stale=len(stale),
        pulled_in=sorted({j.name for j in to_run} - {j.name for j in stale}),
        waves=[[j.name for j in w] for w in waves],
    )

    sem = asyncio.Semaphore(_REFRESH_CONCURRENCY)

    async def _gated(j: IngestJob) -> None:
        async with sem:
            try:
                await run_job(j)
            except Exception as exc:
                log.warning("startup_refresh.job_failed", job=j.name, error=str(exc))

    for i, wave in enumerate(waves):
        await asyncio.gather(*[_gated(j) for j in wave])
        log.info("startup_refresh.wave_complete", wave=i, jobs=len(wave))

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
