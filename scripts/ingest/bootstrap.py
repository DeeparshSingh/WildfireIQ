"""Bootstrap one-shot ingests.

Run this once after `uv sync` to pull all historical and static datasets:
- 25 years of BC historical fires
- ECCC daily climate at Kamloops A (1995–today)
- Open-Meteo ERA5 archive (1999–today)
- ClimateData.ca projections (synthetic placeholder, replaced in Phase 6)

Then runs the recurring jobs once each to populate live snapshots:
- DataBC current fires, FIRMS hotspots, Open-Meteo current, CWFIS FWI,
  ECCC GeoMet AQHI, WAQI pollutants, FireWork smoke metadata, BC evac.

Usage:
    uv run python scripts/ingest/bootstrap.py [--skip-bootstrap] [--skip-live] [--only NAME]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

# Ensure `wildfireiq_api` is importable when running from repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from wildfireiq_api.db import init_db  # noqa: E402
from wildfireiq_api.ingest.base import IngestJob, run_job  # noqa: E402
from wildfireiq_api.ingest.registry import bootstrap_jobs, scheduled_jobs  # noqa: E402


def fmt_status(status: str) -> str:
    return {"ok": "✓", "fail": "✗", "partial": "~"}.get(status, "?")


async def _run(job: IngestJob) -> tuple[str, int, int, str | None]:
    started = time.perf_counter()
    rpt = await run_job(job)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return rpt.status, rpt.rows_written, elapsed_ms, rpt.error or rpt.note


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WildfireIQ ingest bootstrap")
    parser.add_argument("--skip-bootstrap", action="store_true", help="skip one-shot bootstrap jobs")
    parser.add_argument("--skip-live", action="store_true", help="skip live (cron) jobs")
    parser.add_argument("--only", help="run only this single job by name")
    args = parser.parse_args(argv)

    await init_db()

    queue: list[IngestJob] = []
    if args.only:
        from wildfireiq_api.ingest.registry import all_jobs

        jobs = all_jobs()
        if args.only not in jobs:
            print(f"Unknown job: {args.only!r}", file=sys.stderr)
            print(f"Known: {sorted(jobs)}", file=sys.stderr)
            return 2
        queue = [jobs[args.only]]
    else:
        if not args.skip_bootstrap:
            queue.extend(bootstrap_jobs())
        if not args.skip_live:
            queue.extend(scheduled_jobs())

    print("─" * 70)
    print(f"WildfireIQ bootstrap · {len(queue)} job(s)")
    print("─" * 70)

    failures = 0
    for job in queue:
        print(f"\n→ {job.name}  ({job.label or '—'})")
        try:
            status, rows, ms, note = await _run(job)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ crash: {exc}")
            failures += 1
            continue
        glyph = fmt_status(status)
        suffix = f" · {note}" if note else ""
        print(f"  {glyph} {status}  · rows={rows}  · {ms} ms{suffix}")
        if status == "fail":
            failures += 1

    print("\n" + "─" * 70)
    print(f"Done. {len(queue) - failures}/{len(queue)} succeeded.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
