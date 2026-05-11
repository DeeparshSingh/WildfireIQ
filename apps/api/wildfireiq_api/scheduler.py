"""APScheduler wrapper that runs every recurring ingest job on its cadence."""

from __future__ import annotations

import asyncio

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .ingest.base import IngestJob, run_job
from .ingest.registry import scheduled_jobs


log = structlog.get_logger()
_scheduler: AsyncIOScheduler | None = None


def _wrap(job: IngestJob):
    async def runner():
        try:
            await run_job(job)
        except Exception as exc:  # noqa: BLE001
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
