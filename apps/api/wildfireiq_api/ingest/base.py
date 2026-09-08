"""Base class + shared utilities for ingestion jobs."""

from __future__ import annotations

import asyncio
import shutil
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog
from sqlalchemy import text
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .. import __version__
from ..db import session_scope
from ..paths import RAW_ROOT

USER_AGENT: str = (
    f"WildfireIQ/{__version__} "
    f"(research; deeparsh@thompson-rivers; +https://github.com/DeeparshSingh/WildfireIQ)"
)


@dataclass
class IngestReport:
    """Summary returned by an ingest job after it runs."""

    job_name: str
    status: str  # "ok" | "fail" | "partial"
    rows_in: int = 0
    rows_written: int = 0
    bytes_written: int = 0
    duration_ms: int = 0
    note: str | None = None
    error: str | None = None
    artifacts: list[Path] = field(default_factory=list)


@dataclass
class IngestContext:
    """Per-run context passed to a job's run() method."""

    client: httpx.AsyncClient
    log: structlog.BoundLogger
    started_at_utc: datetime


class IngestJob(ABC):
    """One upstream source. Subclasses live in `wildfireiq_api/ingest/`."""

    #: Unique job name. Doubles as the folder under data/raw/.
    name: str

    #: APScheduler cron expression. None for one-shot bootstraps.
    cadence: str | None = None

    #: Human-readable label for logs and the ingest_runs table.
    label: str = ""

    #: How many raw snapshots to keep under data/raw/<name>/. Snapshots are a
    #: debugging aid — they let you replay exactly what an upstream returned —
    #: so a couple of dozen is plenty. Without a cap they grow without bound:
    #: bcem_evac alone writes a GeoJSON every 5 minutes. None keeps everything,
    #: for a job whose raw files *are* the corpus; no current job needs that.
    raw_retention: int | None = 24

    #: Names of jobs whose output this job reads. Cron cadences are staggered
    #: to respect these, but the startup catch-up has no clock to lean on, so
    #: it orders jobs by this graph instead. Naming a bootstrap job is fine:
    #: it is treated as already satisfied once the bootstrap has run.
    depends_on: tuple[str, ...] = ()

    @abstractmethod
    async def run(self, ctx: IngestContext) -> IngestReport:
        """Run a single execution of this job."""
        raise NotImplementedError

    # ── Filesystem helpers ──────────────────────────────────────────

    @property
    def raw_dir(self) -> Path:
        d = RAW_ROOT / self.name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def raw_path(self, *parts: str) -> Path:
        p = self.raw_dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def prune_raw(self) -> int:
        """Delete all but the newest `raw_retention` snapshots. Returns the
        count removed.

        A snapshot is one entry directly under data/raw/<name>/ — a file for
        jobs that write one blob per run, a directory for jobs that write
        several files per run (databc_fires_current, firms_hotspots). Both
        shapes are ordered by modification time, newest kept.
        """
        keep = self.raw_retention
        if keep is None:
            return 0

        d = RAW_ROOT / self.name
        if not d.is_dir():
            return 0

        entries = sorted(d.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        removed = 0
        for entry in entries[keep:]:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            removed += 1
        return removed


# ─── Runner ──────────────────────────────────────────────────────────


async def run_job(job: IngestJob, *, timeout: float = 60.0) -> IngestReport:
    """Run a job with HTTPX, retries, and ingest_runs bookkeeping."""
    log = structlog.get_logger().bind(job=job.name)
    started_at = datetime.now(UTC)
    started_perf = time.perf_counter()

    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
        follow_redirects=True,
    ) as client:
        ctx = IngestContext(client=client, log=log, started_at_utc=started_at)
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1.0, min=1.0, max=10.0),
                retry=retry_if_exception_type(
                    (httpx.HTTPError, asyncio.TimeoutError, ConnectionError),
                ),
                reraise=True,
            ):
                with attempt:
                    report = await job.run(ctx)
                    break
        except RetryError as exc:
            report = IngestReport(
                job_name=job.name,
                status="fail",
                error=f"retries exhausted: {exc!r}",
            )
        except Exception as exc:
            report = IngestReport(
                job_name=job.name,
                status="fail",
                error=f"{type(exc).__name__}: {exc}",
            )

    try:
        pruned = job.prune_raw()
        if pruned:
            log.info("ingest.raw.pruned", removed=pruned, keep=job.raw_retention)
    except OSError as exc:
        log.warning("ingest.raw.prune_failed", error=str(exc))

    report.duration_ms = int((time.perf_counter() - started_perf) * 1000)
    finished_at = datetime.now(UTC)

    log.info(
        "ingest.run.complete",
        status=report.status,
        rows_in=report.rows_in,
        rows_written=report.rows_written,
        duration_ms=report.duration_ms,
        note=report.note,
        error=report.error,
    )

    # Persist to ingest_runs.
    async with session_scope() as session:
        await session.execute(
            text(
                """
                INSERT INTO ingest_runs (
                    job_name, started_at, finished_at, status,
                    rows_in, rows_written, bytes_written, duration_ms,
                    note, error
                ) VALUES (
                    :job_name, :started_at, :finished_at, :status,
                    :rows_in, :rows_written, :bytes_written, :duration_ms,
                    :note, :error
                )
                """
            ),
            {
                "job_name": job.name,
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "status": report.status,
                "rows_in": report.rows_in,
                "rows_written": report.rows_written,
                "bytes_written": report.bytes_written,
                "duration_ms": report.duration_ms,
                "note": report.note,
                "error": report.error,
            },
        )

    return report


# ─── Common parsers ──────────────────────────────────────────────────


def parse_iso(s: str | None) -> datetime | None:
    """Lenient ISO-8601 parse; returns None on failure."""
    if not s:
        return None
    try:
        # Python 3.11+ accepts the "Z" suffix.
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def kvs(d: dict[str, Any], *keys: str) -> Any:
    """Return the first non-None value from `d` matching any of `keys`."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None
