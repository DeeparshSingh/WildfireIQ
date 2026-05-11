"""WAQI (aqicn) Kamloops pollutant breakdown ingest (hourly @ :25)."""

from __future__ import annotations

import pandas as pd

from ..constants import KAMLOOPS_LAT, KAMLOOPS_LON
from ..paths import PROCESSED_ROOT
from ..settings import get_settings
from .base import IngestContext, IngestJob, IngestReport, parse_iso


def _iaqi(iaqi: dict, key: str) -> float | None:
    v = (iaqi.get(key) or {}).get("v")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


class WAQIKamloopsJob(IngestJob):
    name = "waqi_kamloops"
    cadence = "25 * * * *"
    label = "WAQI · Kamloops pollutant breakdown"

    async def run(self, ctx: IngestContext) -> IngestReport:
        token = get_settings().waqi_token
        if not token:
            return IngestReport(
                job_name=self.name,
                status="fail",
                error="WAQI_TOKEN not configured",
            )

        url = f"https://api.waqi.info/feed/geo:{KAMLOOPS_LAT};{KAMLOOPS_LON}/?token={token}"
        ctx.log.info("waqi.fetch")
        r = await ctx.client.get(url)
        r.raise_for_status()
        payload = r.json()

        if payload.get("status") != "ok":
            return IngestReport(
                job_name=self.name,
                status="fail",
                error=f"waqi status={payload.get('status')!r}",
            )

        data = payload.get("data") or {}
        iaqi = data.get("iaqi") or {}
        city = data.get("city") or {}
        geo = city.get("geo") or [None, None]
        obs_dt = parse_iso((data.get("time") or {}).get("iso"))
        obs_iso = obs_dt.isoformat() if obs_dt else (data.get("time") or {}).get("iso")

        row = {
            "station_name": city.get("name"),
            "station_lat": float(geo[0]) if geo and geo[0] is not None else None,
            "station_lon": float(geo[1]) if geo and len(geo) > 1 and geo[1] is not None else None,
            "aqi": pd.to_numeric(data.get("aqi"), errors="coerce"),
            "pm25": _iaqi(iaqi, "pm25"),
            "pm10": _iaqi(iaqi, "pm10"),
            "o3": _iaqi(iaqi, "o3"),
            "no2": _iaqi(iaqi, "no2"),
            "so2": _iaqi(iaqi, "so2"),
            "co": _iaqi(iaqi, "co"),
            "dominant_pollutant": data.get("dominentpol"),
            "observation_time_utc": obs_iso,
            "fetched_at_utc": ctx.started_at_utc.isoformat(),
        }

        new_df = pd.DataFrame([row])

        out_path = PROCESSED_ROOT / "aq_pollutants_recent.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if out_path.exists():
            try:
                existing = pd.read_parquet(out_path)
                merged = pd.concat([existing, new_df], ignore_index=True)
            except Exception as e:  # noqa: BLE001
                ctx.log.info("waqi.existing_read_fail", err=str(e))
                merged = new_df
        else:
            merged = new_df

        merged = merged.drop_duplicates(subset=["fetched_at_utc"]).reset_index(drop=True)
        merged.to_parquet(out_path, compression="zstd", index=False)

        ctx.log.info("waqi.written", rows=len(merged))

        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=1,
            rows_written=len(merged),
            bytes_written=out_path.stat().st_size,
            artifacts=[out_path],
        )
