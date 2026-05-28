"""ClimateData.ca CMIP6 projections bootstrap (one-shot, synthetic).

SYNTHETIC PLACEHOLDER DATA. To be replaced in Phase 6 with real CMIP6
ensembles from ClimateData.ca (the public data API is undocumented). This
job linearly extrapolates the locally-observed ECCC trend so the rest of
the stack has something to render against until then.
"""

from __future__ import annotations

import pandas as pd

from ..paths import PROCESSED_ROOT
from .base import IngestContext, IngestJob, IngestReport

SCENARIOS = {
    "ssp126": 1.5,
    "ssp245": 2.5,
    "ssp585": 4.0,
}
BASELINE_YEAR = 1999
END_YEAR = 2050
OBSERVED_END_YEAR = 2024
DEFAULT_BASELINE_C = 9.0
DEFAULT_OBSERVED_SLOPE = 0.04  # °C / year


def _observed_baseline_and_slope() -> tuple[float, float, dict[int, float]]:
    """Return (baseline_1999_C, observed_slope_C_per_yr, year->observed_mean)."""
    src = PROCESSED_ROOT / "weather_kamloops_archive_daily.parquet"
    if not src.exists():
        return DEFAULT_BASELINE_C, DEFAULT_OBSERVED_SLOPE, {}
    try:
        df = pd.read_parquet(src)
    except Exception:
        return DEFAULT_BASELINE_C, DEFAULT_OBSERVED_SLOPE, {}

    # Look for a temperature column.
    tcol = None
    for cand in ("tmean", "temp_mean", "mean_temp", "tasmean", "temperature_mean"):
        if cand in df.columns:
            tcol = cand
            break
    if tcol is None:
        return DEFAULT_BASELINE_C, DEFAULT_OBSERVED_SLOPE, {}

    dcol = None
    for cand in ("date", "observation_date", "datetime", "day"):
        if cand in df.columns:
            dcol = cand
            break
    if dcol is None:
        return DEFAULT_BASELINE_C, DEFAULT_OBSERVED_SLOPE, {}

    dates = pd.to_datetime(df[dcol], utc=True, errors="coerce")
    years = dates.dt.year
    annual = (
        pd.DataFrame({"year": years, "t": pd.to_numeric(df[tcol], errors="coerce")})
        .dropna()
        .groupby("year")["t"]
        .mean()
    )
    annual = annual[(annual.index >= BASELINE_YEAR) & (annual.index <= OBSERVED_END_YEAR)]
    if len(annual) < 3:
        return DEFAULT_BASELINE_C, DEFAULT_OBSERVED_SLOPE, dict(annual)

    # Linear regression on years.
    xs = annual.index.to_numpy(dtype=float)
    ys = annual.to_numpy(dtype=float)
    slope = float(((xs - xs.mean()) * (ys - ys.mean())).sum() / ((xs - xs.mean()) ** 2).sum())
    intercept = float(ys.mean() - slope * xs.mean())
    baseline = slope * BASELINE_YEAR + intercept
    return baseline, slope, {int(k): float(v) for k, v in annual.items()}


class ClimateDataProjectionsJob(IngestJob):
    name = "climatedata_projections"
    cadence = None
    label = "ClimateData.ca · CMIP6 projections (bootstrap)"

    async def run(self, ctx: IngestContext) -> IngestReport:
        baseline, observed_slope, observed_by_year = _observed_baseline_and_slope()
        ctx.log.info(
            "climateproj.baseline",
            baseline_c=baseline,
            observed_slope=observed_slope,
            n_observed=len(observed_by_year),
        )

        rows: list[dict] = []

        # Observed track (single value, tight uncertainty band).
        for year in range(BASELINE_YEAR, OBSERVED_END_YEAR + 1):
            obs = observed_by_year.get(year, baseline + observed_slope * (year - BASELINE_YEAR))
            band = 0.1
            for variable, offset in (("tasmean", 0.0), ("tasmax", 8.0), ("tasmin", -8.0)):
                v = obs + offset
                rows.append(
                    {
                        "year": year,
                        "ssp": "observed",
                        "variable": variable,
                        "value": v,
                        "q10": v - band,
                        "q50": v,
                        "q90": v + band,
                    }
                )
            # precip: synthetic flat ~ 280 mm/yr baseline, tiny drift
            pr = 280.0 - 0.5 * (year - BASELINE_YEAR)
            rows.append(
                {
                    "year": year,
                    "ssp": "observed",
                    "variable": "pr",
                    "value": pr,
                    "q10": pr - 5,
                    "q50": pr,
                    "q90": pr + 5,
                }
            )

        # Projection tracks. Linear blend: observed slope -> scenario slope post-2025.
        # Each scenario hits baseline + delta by 2050.
        for ssp, delta_2050 in SCENARIOS.items():
            target_2050 = baseline + delta_2050
            for year in range(BASELINE_YEAR, END_YEAR + 1):
                if year <= 2025:
                    t = baseline + observed_slope * (year - BASELINE_YEAR)
                else:
                    # interpolate from 2025 value to 2050 target
                    t_2025 = baseline + observed_slope * (2025 - BASELINE_YEAR)
                    frac = (year - 2025) / (2050 - 2025)
                    t = t_2025 + frac * (target_2050 - t_2025)

                if year <= 2025:
                    band = 0.3
                else:
                    band = 0.3 + 0.02 * (year - 2025)

                for variable, offset in (("tasmean", 0.0), ("tasmax", 8.0), ("tasmin", -8.0)):
                    v = t + offset
                    rows.append(
                        {
                            "year": year,
                            "ssp": ssp,
                            "variable": variable,
                            "value": v,
                            "q10": v - band,
                            "q50": v,
                            "q90": v + band,
                        }
                    )

                # precip: scenario-dependent drift (drier under hotter scenarios).
                pr_slope = {"ssp126": -0.4, "ssp245": -0.9, "ssp585": -1.6}[ssp]
                pr = 280.0 + pr_slope * (year - BASELINE_YEAR)
                pr_band = 5 + 0.4 * max(0, year - 2025)
                rows.append(
                    {
                        "year": year,
                        "ssp": ssp,
                        "variable": "pr",
                        "value": pr,
                        "q10": pr - pr_band,
                        "q50": pr,
                        "q90": pr + pr_band,
                    }
                )

        df = pd.DataFrame(
            rows,
            columns=["year", "ssp", "variable", "value", "q10", "q50", "q90"],
        )
        df["year"] = df["year"].astype(int)

        out_path = PROCESSED_ROOT / "climate_projections.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_path, compression="zstd", index=False)

        ctx.log.info("climateproj.written", rows=len(df))

        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=len(rows),
            rows_written=len(df),
            bytes_written=out_path.stat().st_size,
            note="SYNTHETIC placeholder — replace in Phase 6 with real CMIP6",
            artifacts=[out_path],
        )
