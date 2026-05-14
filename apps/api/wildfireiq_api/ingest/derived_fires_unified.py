"""Nightly rebuild of `data/processed/fires_unified.parquet`.

Concatenates the historical + current fire feeds into a single union
table. Pure derive; cron 02:15 UTC so it runs after both upstream feeds
have settled and before the seasonal-metrics builder (02:30) consumes it.
"""

from __future__ import annotations

import pandas as pd

from ..ml import fires_unified as fu
from .base import IngestContext, IngestJob, IngestReport


class DerivedFiresUnifiedJob(IngestJob):
    name = "derived_fires_unified"
    label = "Derived · unified fires (historical + current)"
    cadence = "15 2 * * *"

    async def run(self, ctx: IngestContext) -> IngestReport:
        ctx.log.info("fires_unified.build.start")
        out = fu.build()
        n = len(pd.read_parquet(out))
        ctx.log.info("fires_unified.build.complete", rows=n, path=str(out))
        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=n,
            rows_written=n,
            artifacts=[out],
            note=f"wrote {out}",
        )
