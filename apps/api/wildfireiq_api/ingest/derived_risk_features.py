"""Nightly rebuild of the wildfire-risk feature artifacts.

Produces the two tables the risk model needs at serving time:

  features_risk_daily.parquet  pooled per-region, per-day feature rows
  cell_density.parquet         per-H3-cell historical fire weights

Depends on `fires_historical.parquet` and every region's daily weather
archive, so this runs after the fires-unified (02:15), Kamloops archive
(02:20), and per-region weather (02:25) jobs.

Without this job the risk grid has no cell density and `/api/risk/grid`
returns 503, so it is part of the scheduled pipeline rather than a manual
step.
"""

from __future__ import annotations

import pandas as pd

from ..ml import features as risk_features
from .base import IngestContext, IngestJob, IngestReport


class DerivedRiskFeaturesJob(IngestJob):
    name = "derived_risk_features"
    cadence = "35 2 * * *"
    label = "Derived · wildfire-risk features + cell density"

    async def run(self, ctx: IngestContext) -> IngestReport:
        ctx.log.info("risk_features.build.start")
        paths = risk_features.build_features()

        n_feat = len(pd.read_parquet(paths["features"]))
        density = pd.read_parquet(paths["density"])
        regions = sorted(density["region"].unique().tolist())

        ctx.log.info(
            "risk_features.build.complete",
            feature_rows=n_feat,
            cells=len(density),
            regions=regions,
        )
        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=n_feat,
            rows_written=n_feat + len(density),
            artifacts=[paths["features"], paths["density"]],
            note=f"{len(density)} cells across {len(regions)} regions",
        )
