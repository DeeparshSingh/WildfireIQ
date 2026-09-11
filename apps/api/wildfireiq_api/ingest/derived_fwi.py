"""Derived Fire Weather Index at representative BC weather stations.

This is the source `/api/fwi/today` serves. It computes FWI ourselves rather
than reading NRCan's published values, because CWFIS carries only 11 stations
inside British Columbia and none of them are the places users search for.
`cwfis_fwi.py` pulls the official numbers alongside, as a cross-check.

How it works:
  1. Pull daily weather from Open-Meteo's archive for each station, from
     1 April of the current year through today — one call per station, no
     key needed.
  2. Run the Van Wagner FWI port already used by the wildfire risk model over
     each station's chronological series.
  3. Persist the *latest* day's row per station as
     `fwi_stations_today.parquet`, the schema /api/fwi/today, the Cesium
     FWIStationsLayer and the LayerDetailModal FwiChecker all read.

Why 1 April and not a rolling window: the three fuel-moisture codes are
carryover values, and they only mean anything if the series starts where the
Van Wagner convention says the season starts. This job used to pull 30 days,
which is fine for FFMC (it responds within a day) and passable for DMC, but
badly wrong for the Drought Code — DC has roughly a 52-day time constant and
accumulates all season. Starting it in August produced DC around 160-235
against NRCan's 439-642 at the same stations, biasing BUI and FWI low in
exactly the dry conditions the index exists to flag.

The port is pure pandas, so this adds no new dependency.

Cron: every 6 hours. FWI is a daily index computed from daily weather, so the
former 30-minute cadence re-derived an unchanged number 48 times a day.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pandas as pd

from ..ml.fwi import compute_fwi
from ..paths import PROCESSED_ROOT
from .base import IngestContext, IngestJob, IngestReport

# Representative BC weather stations (name, lat, lon) — same anchors users
# search for in the location bar and that appear on the BCWS Fire Centre map.
STATIONS: list[tuple[str, float, float]] = [
    ("Kamloops", 50.6745, -120.3273),
    ("Vernon", 50.2671, -119.2720),
    ("Kelowna", 49.8879, -119.4960),
    ("Penticton", 49.4991, -119.5937),
    ("Salmon Arm", 50.7000, -119.2840),
    ("Merritt", 50.1124, -120.7860),
    ("Logan Lake", 50.4929, -120.8082),
    ("Cache Creek", 50.8120, -121.3204),
    ("100 Mile House", 51.6450, -121.2960),
    ("Williams Lake", 52.1417, -122.1417),
    ("Lillooet", 50.6864, -121.9357),
    ("Princeton", 49.4595, -120.5037),
    ("Cranbrook", 49.5097, -115.7660),
    ("Castlegar", 49.3239, -117.6593),
    ("Revelstoke", 50.9981, -118.1957),
    ("Prince George", 53.9171, -122.7497),
    ("Fort St John", 56.2467, -120.8467),
    ("Smithers", 54.7804, -127.1772),
]

#: The archive endpoint, not the forecast one: `past_days` caps at 92, which
#: cannot reach 1 April. Archive covers 1 April through today with no gaps.
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

#: What /api/fwi/today reads.
OUTPUT_NAME = "fwi_stations_today.parquet"

#: Van Wagner's fire season start, and the date `ml.fwi.compute_fwi` assumes
#: its FFMC=85 / DMC=6 / DC=15 startup values apply to.
SEASON_START_MONTH_DAY = (4, 1)


async def _pull_station_weather(
    client, name: str, lat: float, lon: float, *, today: date
) -> pd.DataFrame | None:
    """Daily weather at this station from 1 April through today."""
    season_start = date(today.year, *SEASON_START_MONTH_DAY)
    if today < season_start:
        # Before 1 April there is no current season to spin up; fall back to
        # the previous year's so the codes still carry something real.
        season_start = date(today.year - 1, *SEASON_START_MONTH_DAY)
    params = {
        "latitude": str(lat),
        "longitude": str(lon),
        "start_date": season_start.isoformat(),
        "end_date": today.isoformat(),
        "daily": ",".join(
            [
                "temperature_2m_max",
                "temperature_2m_min",
                "relative_humidity_2m_min",
                "wind_speed_10m_max",
                "precipitation_sum",
                "vapour_pressure_deficit_max",
                "et0_fao_evapotranspiration",
            ]
        ),
        "timezone": "UTC",
    }
    # Open-Meteo rate-limits bursts (HTTP 429). Retry a few times with
    # backoff so we don't silently drop stations on a cold start where all
    # stations fire at once.
    r = None
    for attempt in range(4):
        try:
            r = await client.get(OPEN_METEO_ARCHIVE, params=params)
            if r.status_code == 429:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            break
        except Exception:
            await asyncio.sleep(1.0 * (attempt + 1))
            r = None
    if r is None or r.status_code != 200:
        return None

    j = r.json().get("daily") or {}
    if not j.get("time"):
        return None
    df = pd.DataFrame(
        {
            "day_local": j["time"],
            "temp_max_c": j.get("temperature_2m_max", []),
            "temp_min_c": j.get("temperature_2m_min", []),
            "rh_min_pct": j.get("relative_humidity_2m_min", []),
            "wind_max_kmh": j.get("wind_speed_10m_max", []),
            "precip_mm": j.get("precipitation_sum", []),
            "vpd_max_kpa": j.get("vapour_pressure_deficit_max", []),
            "et0_mm": j.get("et0_fao_evapotranspiration", []),
        }
    )
    df.insert(0, "station_name", name)
    df.insert(1, "latitude", lat)
    df.insert(2, "longitude", lon)
    return df


class DerivedFWIStationsJob(IngestJob):
    name = "derived_fwi_stations"
    cadence = "0 */6 * * *"
    label = "Derived FWI · Van Wagner from Open-Meteo (multi-station BC)"

    async def run(self, ctx: IngestContext) -> IngestReport:
        fetched_at = ctx.started_at_utc.isoformat()

        # Fan out station weather pulls, but cap concurrency at 4 so we
        # don't trip Open-Meteo's burst rate limit (which silently 429s and
        # drops stations). 18 stations / 4 at a time finishes in ~5 batches.
        sem = asyncio.Semaphore(4)

        today = ctx.started_at_utc.date()

        async def _gated(name: str, lat: float, lon: float):
            async with sem:
                return await _pull_station_weather(ctx.client, name, lat, lon, today=today)

        tasks = [_gated(name, lat, lon) for name, lat, lon in STATIONS]
        frames = await asyncio.gather(*tasks)
        good = [f for f in frames if f is not None and not f.empty]
        if not good:
            return IngestReport(
                job_name=self.name,
                status="fail",
                error="all station weather pulls returned empty",
            )

        rows: list[dict] = []
        for f in good:
            # Compute the FWI carryover series for this station's history.
            with_fwi = compute_fwi(f)
            # Latest non-NaN row.
            last = with_fwi.dropna(subset=["fwi"]).tail(1)
            if last.empty:
                continue
            r = last.iloc[0]
            rows.append(
                {
                    "station_id": r["station_name"].replace(" ", "_").lower(),
                    "station_name": r["station_name"],
                    "agency": "WildfireIQ derived (Open-Meteo + Van Wagner)",
                    "latitude": float(r["latitude"]),
                    "longitude": float(r["longitude"]),
                    "observation_date_local": str(pd.to_datetime(r["day_local"]).date()),
                    "temp_c": float(r["temp_max_c"]) if pd.notna(r["temp_max_c"]) else None,
                    "rh_pct": float(r["rh_min_pct"]) if pd.notna(r["rh_min_pct"]) else None,
                    "wind_kmh": float(r["wind_max_kmh"]) if pd.notna(r["wind_max_kmh"]) else None,
                    "precip_mm": float(r["precip_mm"]) if pd.notna(r["precip_mm"]) else None,
                    "ffmc": float(r["ffmc"]),
                    "dmc": float(r["dmc"]),
                    "dc": float(r["dc"]),
                    "isi": float(r["isi"]),
                    "bui": float(r["bui"]),
                    "fwi": float(r["fwi"]),
                    "dsr": float(r["dsr"]),
                    "fetched_at_utc": fetched_at,
                }
            )

        df = pd.DataFrame(rows)
        out_path = PROCESSED_ROOT / OUTPUT_NAME
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_path, compression="zstd", index=False)
        ctx.log.info("derived_fwi.written", rows=len(df), path=str(out_path))

        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=len(STATIONS),
            rows_written=len(df),
            bytes_written=out_path.stat().st_size,
            artifacts=[out_path],
        )
