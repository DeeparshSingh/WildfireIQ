"""Per-region daily weather archives for the multi-region risk model.

Builds an ERA5 history (1999 to a few days ago) spliced with the recent
observed tail from the forecast endpoint for each modelled region's anchor
city, so every region's daily series reaches today. Kamloops keeps its own
job (open_meteo_archive_kamloops); this job covers the other regions.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pandas as pd

from ..constants import REGIONS
from ..paths import PROCESSED_ROOT
from .base import IngestContext, IngestJob, IngestReport
from .open_meteo import ARCHIVE_URL, FORECAST_URL, _DAILY_VARS, _daily_frame


async def build_region_weather(client, lat: float, lon: float, out_path) -> int:
    """Pull ERA5 history + recent observed tail for one point; write parquet."""
    today = datetime.now(timezone.utc).date()
    yesterday = (today - timedelta(days=1)).isoformat()

    archive_params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": "1999-01-01",
        "end_date": yesterday,
        "daily": _DAILY_VARS,
        "timezone": "America/Vancouver",
    }
    r = await client.get(ARCHIVE_URL, params=archive_params, timeout=120.0)
    r.raise_for_status()
    df = _daily_frame(r.json().get("daily") or {})

    # Recent observed tail (forecast endpoint reaches today; ERA5 lags ~5 days).
    tail_params = {
        "latitude": lat,
        "longitude": lon,
        "daily": _DAILY_VARS,
        "past_days": 15,
        "forecast_days": 1,
        "timezone": "America/Vancouver",
    }
    try:
        rt = await client.get(FORECAST_URL, params=tail_params, timeout=60.0)
        rt.raise_for_status()
        tail = _daily_frame(rt.json().get("daily") or {})
        if not tail.empty:
            df = pd.concat([df, tail], ignore_index=True)
            df["day_local"] = df["day_local"].astype(str)
            df = df.drop_duplicates(subset=["day_local"], keep="last")
    except Exception:
        pass

    df = df.sort_values("day_local").reset_index(drop=True)
    df = df[df["temp_max_c"].notna()].reset_index(drop=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, compression="zstd", index=False)
    return len(df)


class DerivedRegionWeatherJob(IngestJob):
    name = "derived_region_weather"
    cadence = "25 2 * * *"  # after the Kamloops archive job (20 2)
    label = "Derived · per-region weather archives"

    async def run(self, ctx: IngestContext) -> IngestReport:
        built: dict[str, int] = {}
        targets = [r for r in REGIONS if r["key"] != "thompson_okanagan"]
        for i, reg in enumerate(targets):
            # Space the heavy 27-year archive pulls out so Open-Meteo's burst
            # limit (HTTP 429) doesn't drop a region.
            if i > 0:
                await asyncio.sleep(8)
            out = PROCESSED_ROOT / reg["weather_file"]
            try:
                n = await build_region_weather(ctx.client, reg["lat"], reg["lon"], out)
                built[reg["key"]] = n
                ctx.log.info("region_weather.built", region=reg["key"], rows=n)
            except Exception as exc:  # noqa: BLE001
                ctx.log.warning("region_weather.failed", region=reg["key"], error=str(exc))

        total = sum(built.values())
        return IngestReport(
            job_name=self.name,
            status="ok" if built else "fail",
            rows_in=total,
            rows_written=total,
            note="; ".join(f"{k}={v}" for k, v in built.items()),
        )
