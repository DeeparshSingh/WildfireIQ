"""Per-region daily weather archives for the multi-region risk model.

Builds an ERA5 history (1999 to a few days ago) spliced with the recent
observed tail from the forecast endpoint for each modelled region's anchor
city, so every region's daily series reaches today. Kamloops keeps its own
job (open_meteo_archive_kamloops); this job covers the other regions.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pandas as pd

from ..constants import REGIONS
from ..paths import PROCESSED_ROOT
from .base import IngestContext, IngestJob, IngestReport
from .open_meteo import _DAILY_VARS, ARCHIVE_URL, FORECAST_URL, _daily_frame

#: Waits between retries of a rate-limited archive pull. Open-Meteo's burst
#: limit clears in well under a minute, and this job is nightly, so waiting is
#: cheaper than losing a region for a day.
_RATE_LIMIT_BACKOFF: tuple[float, ...] = (12.0, 30.0, 60.0)


async def _get_with_backoff(client, url: str, params: dict, timeout: float):
    """GET, retrying an HTTP 429 with a widening wait. Other errors raise."""
    last: httpx.HTTPStatusError | None = None
    for wait in (0.0, *_RATE_LIMIT_BACKOFF):
        if wait:
            await asyncio.sleep(wait)
        r = await client.get(url, params=params, timeout=timeout)
        try:
            r.raise_for_status()
            return r
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429:
                raise
            last = exc
    assert last is not None
    raise last


async def build_region_weather(client, lat: float, lon: float, out_path, log=None) -> int:
    """Pull ERA5 history + recent observed tail for one point; write parquet."""
    today = datetime.now(UTC).date()
    yesterday = (today - timedelta(days=1)).isoformat()

    archive_params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": "1999-01-01",
        "end_date": yesterday,
        "daily": _DAILY_VARS,
        "timezone": "America/Vancouver",
    }
    r = await _get_with_backoff(client, ARCHIVE_URL, archive_params, timeout=120.0)
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
        rt = await _get_with_backoff(client, FORECAST_URL, tail_params, timeout=60.0)
        tail = _daily_frame(rt.json().get("daily") or {})
        if not tail.empty:
            df = pd.concat([df, tail], ignore_index=True)
            df["day_local"] = df["day_local"].astype(str)
            df = df.drop_duplicates(subset=["day_local"], keep="last")
    except Exception as exc:
        # ERA5 alone still trains the model, but without the tail the series
        # stops ~5 days short and the risk grid would quietly score stale
        # weather. Say so rather than swallowing it.
        if log is not None:
            log.warning("region_weather.tail_missing", lat=lat, lon=lon, error=str(exc))

    df = df.sort_values("day_local").reset_index(drop=True)
    df = df[df["temp_max_c"].notna()].reset_index(drop=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, compression="zstd", index=False)
    return len(df)


class DerivedRegionWeatherJob(IngestJob):
    name = "derived_region_weather"
    cadence = "25 2 * * *"  # after the Kamloops archive job (20 2)
    label = "Derived · per-region weather archives"
    # Not a data dependency: this job issues the same heavy 27-year archive
    # query against the same rate-limited host, so overlapping the two earns an
    # HTTP 429 and loses a region. Ordering them keeps both intact.
    depends_on = ("open_meteo_archive_kamloops",)

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
                n = await build_region_weather(ctx.client, reg["lat"], reg["lon"], out, log=ctx.log)
                built[reg["key"]] = n
                ctx.log.info("region_weather.built", region=reg["key"], rows=n)
            except Exception as exc:
                ctx.log.warning("region_weather.failed", region=reg["key"], error=str(exc))

        total = sum(built.values())
        missing = [r["key"] for r in targets if r["key"] not in built]
        if not built:
            status = "fail"
        elif missing:
            status = "partial"
        else:
            status = "ok"

        note = "; ".join(f"{k}={v}" for k, v in built.items())
        if missing:
            # Name the gap: a region left out keeps serving its previous archive,
            # and that is worth seeing in /api/admin/ingest rather than guessing.
            note = f"{note}; stale={','.join(missing)}" if note else f"stale={','.join(missing)}"

        return IngestReport(
            job_name=self.name,
            status=status,
            rows_in=total,
            rows_written=total,
            note=note,
        )
