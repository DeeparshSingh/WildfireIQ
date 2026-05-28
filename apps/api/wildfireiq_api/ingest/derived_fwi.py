"""Derived Fire Weather Index — multi-station fallback when CWFIS is down.

NRCan's CWFIS GeoServer has been HTTP-502 throughout the build. This job
computes FWI ourselves at a curated set of representative BC weather
stations by:
  1. Pulling the last 30 days of daily weather from Open-Meteo for each
     station coordinate (free, no key, 10 stations = 10 API calls per run).
  2. Running the Van Wagner FWI port already used by the wildfire risk
     model on each station's chronological series so carryover codes
     (FFMC/DMC/DC) are valid.
  3. Persisting the *latest* day's row per station as
     `fwi_stations_today.parquet` — same schema the CWFIS job uses, so
     the existing /api/fwi/today route + the Cesium FWIStationsLayer +
     LayerDetailModal FwiBrowser all work unchanged.

This is the "Phase 3 stretch" listed in the wildfire risk model card and
called out in logic.md (`cffdrs-py` port).  We use our own pure-pandas
port so there's no new dependency.

Cron: every 30 min (cheap, ~3 s to run).
"""

from __future__ import annotations

import asyncio

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

OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"


async def _pull_station_weather(
    client, name: str, lat: float, lon: float
) -> pd.DataFrame | None:
    """Pull last 30 days of daily weather at this station."""
    # Use the forecast endpoint with `past_days=30` so we always get
    # the most up-to-date rows including yesterday (Archive lags ~5 days).
    params = {
        "latitude": str(lat),
        "longitude": str(lon),
        "daily": ",".join([
            "temperature_2m_max",
            "temperature_2m_min",
            "relative_humidity_2m_min",
            "wind_speed_10m_max",
            "precipitation_sum",
            "vapour_pressure_deficit_max",
            "et0_fao_evapotranspiration",
        ]),
        "past_days": "30",
        "forecast_days": "1",
        "timezone": "UTC",
    }
    # Open-Meteo rate-limits bursts (HTTP 429). Retry a few times with
    # backoff so we don't silently drop stations on a cold start where all
    # stations fire at once.
    r = None
    for attempt in range(4):
        try:
            r = await client.get(OPEN_METEO_FORECAST, params=params)
            if r.status_code == 429:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            break
        except Exception:  # noqa: BLE001
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
    cadence = "*/30 * * * *"
    label = "Derived FWI · Van Wagner from Open-Meteo (multi-station BC)"

    async def run(self, ctx: IngestContext) -> IngestReport:
        fetched_at = ctx.started_at_utc.isoformat()

        # Fan out station weather pulls, but cap concurrency at 4 so we
        # don't trip Open-Meteo's burst rate limit (which silently 429s and
        # drops stations). 18 stations / 4 at a time finishes in ~5 batches.
        sem = asyncio.Semaphore(4)

        async def _gated(name: str, lat: float, lon: float):
            async with sem:
                return await _pull_station_weather(ctx.client, name, lat, lon)

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
        out_path = PROCESSED_ROOT / "fwi_stations_today.parquet"
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
