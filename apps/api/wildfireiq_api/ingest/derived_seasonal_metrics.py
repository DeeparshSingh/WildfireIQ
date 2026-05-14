"""Nightly rebuild of `data/processed/seasonal_metrics.parquet` for Phase 6.

Joins historical fires + Open-Meteo archive daily wx + a fresh Van Wagner
FWI run, producing one row per fire-season year. Runs after the upstream
ingest jobs have settled (cron 02:30 UTC).
"""

from __future__ import annotations

import pandas as pd

from ..ml import seasonal_metrics as sm
from .base import IngestContext, IngestJob, IngestReport


class DerivedSeasonalMetricsJob(IngestJob):
    name = "derived_seasonal_metrics"
    label = "Derived · seasonal climate+fire metrics"
    cadence = "30 2 * * *"  # 02:30 UTC daily

    async def run(self, ctx: IngestContext) -> IngestReport:
        ctx.log.info("seasonal_metrics.build.start")
        out_path = sm.build()
        n = len(pd.read_parquet(out_path))
        ctx.log.info("seasonal_metrics.build.complete", rows=n, path=str(out_path))
        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=n,
            rows_written=n,
            artifacts=[out_path],
            note=f"wrote {out_path}",
        )
