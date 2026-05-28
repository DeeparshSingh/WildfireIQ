"""Open-Meteo Air Quality archive + forecast ingest.

Open-Meteo's `air-quality-api.open-meteo.com` returns hourly pollutant
concentrations (PM2.5, PM10, O3, NO2, SO2, CO) plus the European AQI for any
lat/lon. The free tier supports up to 92 days back + 5 days forward.

We also co-locate weather features (temp, RH, wind, precip) from the same
provider so the AQ forecaster trains on coherent rows without joining
parquets across sources.

Output: `data/processed/aq_hourly_kamloops.parquet` — UPSERT on `time_utc`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from ..constants import KAMLOOPS_LAT, KAMLOOPS_LON
from ..paths import PROCESSED_ROOT
from .base import IngestContext, IngestJob, IngestReport

AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WX_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


class OpenMeteoAQHourlyJob(IngestJob):
    """Hourly cron — pulls last 7 days actual + next 5 days forecast.
    The historical bootstrap (92 days) is run separately on first install."""

    name = "open_meteo_aq_hourly"
    cadence = "15 * * * *"  # 15 min past each hour, AFTER weather job's :05
    label = "Open-Meteo · Kamloops air quality hourly + 5d forecast"

    past_days = 7
    forecast_days = 5

    async def run(self, ctx: IngestContext) -> IngestReport:
        return await _run(self, ctx)


class OpenMeteoAQArchiveJob(IngestJob):
    """Bootstrap + nightly top-up — 365 days back.

    The air-quality `past_days` parameter is capped at 92 by Open-Meteo, so
    for a full year we pass an explicit `start_date`/`end_date` range. CAMS
    reanalysis is available from 2022-07-29 onward, so a 365-day window is
    always satisfiable. Weather features for the same window come from the
    ERA5 archive endpoint (which also accepts the date range).

    Runs nightly so the smoke-event calendar always covers a rolling year.
    """

    name = "open_meteo_aq_archive"
    cadence = "40 2 * * *"  # 02:40 UTC, after the other derived jobs
    label = "Open-Meteo · Kamloops AQ archive (365 days)"

    past_days = 92  # unused in date-range mode; kept for the shared _run signature
    forecast_days = 0
    archive_days = 365  # triggers start_date/end_date mode

    async def run(self, ctx: IngestContext) -> IngestReport:
        return await _run(self, ctx)


async def _run(job: OpenMeteoAQHourlyJob | OpenMeteoAQArchiveJob, ctx: IngestContext) -> IngestReport:
    fetched_at = ctx.started_at_utc.isoformat()

    # Archive mode uses an explicit date range (past_days is capped at 92 by
    # the AQ endpoint); the hourly cron uses past_days/forecast_days.
    archive_days = getattr(job, "archive_days", None)
    if archive_days:
        end = datetime.now(UTC).date()
        start = end - pd.Timedelta(days=archive_days)
        range_params = {"start_date": start.isoformat(), "end_date": end.isoformat()}
        wx_url = ARCHIVE_URL  # ERA5 archive supports the long window
    else:
        range_params = {"past_days": str(job.past_days), "forecast_days": str(job.forecast_days)}
        wx_url = WX_URL

    # ── 1. Pull air quality ────────────────────────────────────────
    aq_params = {
        "latitude": str(KAMLOOPS_LAT),
        "longitude": str(KAMLOOPS_LON),
        "hourly": ",".join([
            "pm2_5",
            "pm10",
            "carbon_monoxide",
            "nitrogen_dioxide",
            "sulphur_dioxide",
            "ozone",
            "european_aqi",
        ]),
        "timezone": "UTC",
        **range_params,
    }
    ctx.log.info("openmeteo_aq.fetch", mode="archive" if archive_days else "hourly", **range_params)
    r = await ctx.client.get(AQ_URL, params=aq_params)
    r.raise_for_status()
    aq = r.json().get("hourly", {})
    if not aq.get("time"):
        return IngestReport(job_name=job.name, status="fail", error="empty AQ response")

    # ── 2. Pull co-located weather (same range) ───────────────────
    wx_params = {
        "latitude": str(KAMLOOPS_LAT),
        "longitude": str(KAMLOOPS_LON),
        "hourly": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "wind_speed_10m",
            "wind_direction_10m",
            "precipitation",
            "boundary_layer_height",
        ]),
        "timezone": "UTC",
        **range_params,
    }
    rw = await ctx.client.get(wx_url, params=wx_params)
    rw.raise_for_status()
    wx = rw.json().get("hourly", {})

    # ── 3. Build dataframe ─────────────────────────────────────────
    df = pd.DataFrame(
        {
            "time_utc": aq["time"],
            "pm2_5": aq.get("pm2_5", []),
            "pm10": aq.get("pm10", []),
            "co": aq.get("carbon_monoxide", []),
            "no2": aq.get("nitrogen_dioxide", []),
            "so2": aq.get("sulphur_dioxide", []),
            "o3": aq.get("ozone", []),
            "european_aqi": aq.get("european_aqi", []),
        }
    )
    if wx.get("time"):
        wx_df = pd.DataFrame(
            {
                "time_utc": wx["time"],
                "temp_c": wx.get("temperature_2m", []),
                "rh_pct": wx.get("relative_humidity_2m", []),
                "wind_kmh": wx.get("wind_speed_10m", []),
                "wind_dir": wx.get("wind_direction_10m", []),
                "precip_mm": wx.get("precipitation", []),
                "boundary_layer_m": wx.get("boundary_layer_height", []),
            }
        )
        df = df.merge(wx_df, on="time_utc", how="left")

    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=False).dt.tz_localize("UTC")
    df["fetched_at_utc"] = fetched_at

    # ── 4. Upsert into the existing parquet ────────────────────────
    out_path = PROCESSED_ROOT / "aq_hourly_kamloops.parquet"
    if out_path.exists():
        try:
            prev = pd.read_parquet(out_path)
            prev["time_utc"] = pd.to_datetime(prev["time_utc"], utc=True)
            df = pd.concat([prev, df], ignore_index=True)
            df = df.sort_values("time_utc").drop_duplicates(
                subset=["time_utc"], keep="last"
            )
        except Exception as exc:
            ctx.log.info("openmeteo_aq.upsert_failed", error=str(exc))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, compression="zstd", index=False)
    ctx.log.info("openmeteo_aq.written", rows=len(df), path=str(out_path))

    return IngestReport(
        job_name=job.name,
        status="ok",
        rows_in=len(aq.get("time", [])),
        rows_written=len(df),
        bytes_written=out_path.stat().st_size,
        artifacts=[out_path],
    )
