"""Open-Meteo Kamloops weather ingest (forecast + ERA5 archive bootstrap)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from ..constants import KAMLOOPS_LAT, KAMLOOPS_LON
from ..paths import PROCESSED_ROOT
from .base import IngestContext, IngestJob, IngestReport


FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


class OpenMeteoKamloopsJob(IngestJob):
    name = "open_meteo_kamloops"
    cadence = "5 * * * *"
    label = "Open-Meteo · Kamloops weather"

    async def run(self, ctx: IngestContext) -> IngestReport:
        fetched_at = ctx.started_at_utc.isoformat()
        params = {
            "latitude": KAMLOOPS_LAT,
            "longitude": KAMLOOPS_LON,
            "current": (
                "temperature_2m,relative_humidity_2m,wind_speed_10m,"
                "wind_direction_10m,wind_gusts_10m,precipitation,"
                "vapour_pressure_deficit"
            ),
            "hourly": (
                "temperature_2m,relative_humidity_2m,wind_speed_10m,"
                "wind_gusts_10m,wind_direction_10m,precipitation,"
                "vapour_pressure_deficit,et0_fao_evapotranspiration"
            ),
            "daily": (
                "temperature_2m_max,temperature_2m_min,relative_humidity_2m_min,"
                "precipitation_sum,wind_speed_10m_max,wind_gusts_10m_max,"
                "et0_fao_evapotranspiration"
            ),
            "past_days": 2,
            "forecast_days": 10,
            "timezone": "America/Vancouver",
            "models": "gem_hrdps_continental",
        }

        ctx.log.info("open_meteo.fetch", endpoint="forecast")
        r = await ctx.client.get(FORECAST_URL, params=params)
        r.raise_for_status()
        data = r.json()

        artifacts: list = []
        rows_written = 0
        bytes_written = 0

        # ── Current snapshot ──
        cur = data.get("current") or {}
        cur_row = {
            "temp_c": cur.get("temperature_2m"),
            "rh_pct": cur.get("relative_humidity_2m"),
            "wind_kmh": cur.get("wind_speed_10m"),
            "wind_dir_deg": cur.get("wind_direction_10m"),
            "wind_gust_kmh": cur.get("wind_gusts_10m"),
            "precip_mm": cur.get("precipitation"),
            "vpd_kpa": cur.get("vapour_pressure_deficit"),
            "observed_at_local": cur.get("time"),
            "fetched_at_utc": fetched_at,
        }
        df_cur = pd.DataFrame([cur_row])
        cur_path = PROCESSED_ROOT / "weather_kamloops_current.parquet"
        cur_path.parent.mkdir(parents=True, exist_ok=True)
        df_cur.to_parquet(cur_path, compression="zstd", index=False)
        artifacts.append(cur_path)
        rows_written += len(df_cur)
        bytes_written += cur_path.stat().st_size

        # ── Hourly ──
        hourly = data.get("hourly") or {}
        times = hourly.get("time") or []
        now_local_str = cur.get("time") or ""
        df_h = pd.DataFrame(
            {
                "ts_local": times,
                "temp_c": hourly.get("temperature_2m") or [None] * len(times),
                "rh_pct": hourly.get("relative_humidity_2m") or [None] * len(times),
                "wind_kmh": hourly.get("wind_speed_10m") or [None] * len(times),
                "wind_gust_kmh": hourly.get("wind_gusts_10m") or [None] * len(times),
                "wind_dir_deg": hourly.get("wind_direction_10m") or [None] * len(times),
                "precip_mm": hourly.get("precipitation") or [None] * len(times),
                "vpd_kpa": hourly.get("vapour_pressure_deficit") or [None] * len(times),
                "et0_mm": hourly.get("et0_fao_evapotranspiration") or [None] * len(times),
            }
        )
        if not df_h.empty:
            df_h["ts_utc"] = pd.to_datetime(df_h["ts_local"], errors="coerce").dt.tz_localize(
                "America/Vancouver", ambiguous="NaT", nonexistent="NaT"
            ).dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%S%z")
            df_h["is_forecast"] = df_h["ts_local"] >= now_local_str
        df_h = df_h[
            [
                "ts_local",
                "ts_utc",
                "temp_c",
                "rh_pct",
                "wind_kmh",
                "wind_gust_kmh",
                "wind_dir_deg",
                "precip_mm",
                "vpd_kpa",
                "et0_mm",
                "is_forecast",
            ]
        ]
        hourly_path = PROCESSED_ROOT / "weather_kamloops_hourly.parquet"
        df_h.to_parquet(hourly_path, compression="zstd", index=False)
        artifacts.append(hourly_path)
        rows_written += len(df_h)
        bytes_written += hourly_path.stat().st_size

        # ── Daily ──
        daily = data.get("daily") or {}
        days = daily.get("time") or []
        today_local = (cur.get("time") or "")[:10]
        df_d = pd.DataFrame(
            {
                "day_local": days,
                "temp_max_c": daily.get("temperature_2m_max") or [None] * len(days),
                "temp_min_c": daily.get("temperature_2m_min") or [None] * len(days),
                "rh_min_pct": daily.get("relative_humidity_2m_min") or [None] * len(days),
                "precip_mm": daily.get("precipitation_sum") or [None] * len(days),
                "wind_max_kmh": daily.get("wind_speed_10m_max") or [None] * len(days),
                "wind_gust_max_kmh": daily.get("wind_gusts_10m_max") or [None] * len(days),
                "et0_mm": daily.get("et0_fao_evapotranspiration") or [None] * len(days),
            }
        )
        if not df_d.empty:
            df_d["is_forecast"] = df_d["day_local"] >= today_local
        daily_path = PROCESSED_ROOT / "weather_kamloops_daily.parquet"
        df_d.to_parquet(daily_path, compression="zstd", index=False)
        artifacts.append(daily_path)
        rows_written += len(df_d)
        bytes_written += daily_path.stat().st_size

        ctx.log.info(
            "open_meteo.written",
            current=len(df_cur),
            hourly=len(df_h),
            daily=len(df_d),
        )

        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=len(df_h) + len(df_d) + len(df_cur),
            rows_written=rows_written,
            bytes_written=bytes_written,
            artifacts=artifacts,
        )


class OpenMeteoArchiveBootstrapJob(IngestJob):
    name = "open_meteo_archive_kamloops"
    cadence = None
    label = "Open-Meteo ERA5 archive · Kamloops bootstrap"

    async def run(self, ctx: IngestContext) -> IngestReport:
        yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        params = {
            "latitude": KAMLOOPS_LAT,
            "longitude": KAMLOOPS_LON,
            "start_date": "1999-01-01",
            "end_date": yesterday,
            "daily": (
                "temperature_2m_max,temperature_2m_min,relative_humidity_2m_min,"
                "precipitation_sum,wind_speed_10m_max,wind_gusts_10m_max,"
                "et0_fao_evapotranspiration,vapour_pressure_deficit_max"
            ),
            "timezone": "America/Vancouver",
        }
        ctx.log.info("open_meteo.archive.fetch", end_date=yesterday)
        r = await ctx.client.get(ARCHIVE_URL, params=params, timeout=120.0)
        r.raise_for_status()
        data = r.json()
        daily = data.get("daily") or {}
        days = daily.get("time") or []
        df = pd.DataFrame(
            {
                "day_local": days,
                "temp_max_c": daily.get("temperature_2m_max") or [None] * len(days),
                "temp_min_c": daily.get("temperature_2m_min") or [None] * len(days),
                "rh_min_pct": daily.get("relative_humidity_2m_min") or [None] * len(days),
                "precip_mm": daily.get("precipitation_sum") or [None] * len(days),
                "wind_max_kmh": daily.get("wind_speed_10m_max") or [None] * len(days),
                "wind_gust_max_kmh": daily.get("wind_gusts_10m_max") or [None] * len(days),
                "et0_mm": daily.get("et0_fao_evapotranspiration") or [None] * len(days),
                "vpd_max_kpa": daily.get("vapour_pressure_deficit_max") or [None] * len(days),
            }
        )
        out = PROCESSED_ROOT / "weather_kamloops_archive_daily.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, compression="zstd", index=False)
        ctx.log.info("open_meteo.archive.written", rows=len(df), path=str(out))
        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=len(df),
            rows_written=len(df),
            bytes_written=out.stat().st_size,
            artifacts=[out],
        )
