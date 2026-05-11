"""ECCC Kamloops climate bulk bootstrap (one-time)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from io import StringIO

import pandas as pd

from ..constants import KAMLOOPS_A_STATION_ID
from ..paths import PROCESSED_ROOT
from .base import IngestContext, IngestJob, IngestReport


BULK_URL = "https://climate.weather.gc.ca/climate_data/bulk_data_e.html"


def _pick(df: pd.DataFrame, *candidates: str) -> pd.Series | None:
    """Return first matching column, handling degree-symbol variants."""
    cols = {c: c for c in df.columns}
    # Normalize degree variants
    norm_map = {c.replace("\xb0", "°"): c for c in df.columns}
    for cand in candidates:
        if cand in cols:
            return df[cand]
        if cand in norm_map:
            return df[norm_map[cand]]
    return None


class ECCCClimateBulkJob(IngestJob):
    name = "eccc_climate_kamloops"
    cadence = None
    label = "ECCC · Kamloops climate bulk (bootstrap)"

    async def run(self, ctx: IngestContext) -> IngestReport:
        current_year = datetime.now(timezone.utc).year
        frames: list[pd.DataFrame] = []
        artifacts: list = []
        rows_total = 0

        for year in range(1995, current_year + 1):
            params = {
                "format": "csv",
                "stationID": str(KAMLOOPS_A_STATION_ID),
                "Year": str(year),
                "Month": "1",
                "timeframe": "2",
            }
            ctx.log.info("eccc.fetch", year=year)
            try:
                r = await ctx.client.get(BULK_URL, params=params, timeout=60.0)
                r.raise_for_status()
            except Exception as exc:  # noqa: BLE001
                ctx.log.info("eccc.fetch_failed", year=year, error=str(exc))
                await asyncio.sleep(0.5)
                continue

            text_body = r.content.decode("utf-8-sig", errors="replace")
            raw_path = self.raw_path(f"{year}.csv")
            raw_path.write_text(text_body, encoding="utf-8")
            artifacts.append(raw_path)

            try:
                df = pd.read_csv(StringIO(text_body), header=0, low_memory=False)
            except Exception as exc:  # noqa: BLE001
                ctx.log.info("eccc.parse_failed", year=year, error=str(exc))
                await asyncio.sleep(0.5)
                continue

            if df.empty:
                ctx.log.info("eccc.empty_year", year=year)
                await asyncio.sleep(0.5)
                continue

            date_col = _pick(df, "Date/Time", "Date/Time (LST)")
            year_col = _pick(df, "Year")
            month_col = _pick(df, "Month")
            day_col = _pick(df, "Day")
            tmax = _pick(df, "Max Temp (°C)", "Max Temp (\xb0C)")
            tmin = _pick(df, "Min Temp (°C)", "Min Temp (\xb0C)")
            tmean = _pick(df, "Mean Temp (°C)", "Mean Temp (\xb0C)")
            precip = _pick(df, "Total Precip (mm)")
            rain = _pick(df, "Total Rain (mm)")
            snow = _pick(df, "Total Snow (cm)")
            snow_ground = _pick(df, "Snow on Grnd (cm)")
            gust = _pick(df, "Spd of Max Gust (km/h)")

            n = len(df)
            norm = pd.DataFrame(
                {
                    "day_local": date_col if date_col is not None else [None] * n,
                    "year": year_col if year_col is not None else [year] * n,
                    "month": month_col if month_col is not None else [None] * n,
                    "day": day_col if day_col is not None else [None] * n,
                    "temp_max_c": pd.to_numeric(tmax, errors="coerce")
                    if tmax is not None
                    else [None] * n,
                    "temp_min_c": pd.to_numeric(tmin, errors="coerce")
                    if tmin is not None
                    else [None] * n,
                    "temp_mean_c": pd.to_numeric(tmean, errors="coerce")
                    if tmean is not None
                    else [None] * n,
                    "precip_mm": pd.to_numeric(precip, errors="coerce")
                    if precip is not None
                    else [None] * n,
                    "rain_mm": pd.to_numeric(rain, errors="coerce")
                    if rain is not None
                    else [None] * n,
                    "snow_cm": pd.to_numeric(snow, errors="coerce")
                    if snow is not None
                    else [None] * n,
                    "snow_on_ground_cm": pd.to_numeric(snow_ground, errors="coerce")
                    if snow_ground is not None
                    else [None] * n,
                    "spd_max_gust_kmh": pd.to_numeric(gust, errors="coerce")
                    if gust is not None
                    else [None] * n,
                    "station_id": [KAMLOOPS_A_STATION_ID] * n,
                }
            )
            frames.append(norm)
            rows_total += n
            ctx.log.info("eccc.fetched_year", year=year, rows=n)
            await asyncio.sleep(0.5)

        if frames:
            big = pd.concat(frames, ignore_index=True)
        else:
            big = pd.DataFrame()
        out = PROCESSED_ROOT / "weather_kamloops_eccc_daily.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        big.to_parquet(out, compression="zstd", index=False)
        artifacts.append(out)
        ctx.log.info("eccc.written", rows=len(big), path=str(out))

        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=rows_total,
            rows_written=len(big),
            bytes_written=out.stat().st_size,
            artifacts=artifacts,
        )
