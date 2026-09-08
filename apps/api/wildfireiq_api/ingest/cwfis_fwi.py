"""NRCan CWFIS Fire Weather Index daily ingest.

Real station observations from NRCan, as an independent cross-check on the
Van Wagner FWI this project computes itself in `derived_fwi`. That derived
job — not this one — is what `/api/fwi/today` serves: it covers the 18 BC
locations users actually search for and refreshes every 30 minutes, where
CWFIS carries only 11 BC stations and publishes once a day.

This job had been failing for the whole build against a diagnosis that was
simply wrong. The error said the GeoServer was unreachable and the code
comments blamed recurring HTTP 502s. The host was up the entire time: NRCan
renamed the layer from `public:fwi_stns_current` to `public:firewx_stns_current`,
and every request had been coming back as a WFS `InvalidParameterValue`
exception, which the broad `except` treated as an outage.
"""

from __future__ import annotations

import json

import httpx
import pandas as pd

from ..constants import (
    BC_BBOX_EAST as BBOX_EAST,
)
from ..constants import (
    BC_BBOX_NORTH as BBOX_NORTH,
)
from ..constants import (
    BC_BBOX_SOUTH as BBOX_SOUTH,
)
from ..constants import (
    BC_BBOX_WEST as BBOX_WEST,
)
from ..paths import PROCESSED_ROOT
from .base import IngestContext, IngestJob, IngestReport, kvs

WFS_URL = "https://cwfis.cfs.nrcan.gc.ca/geoserver/public/ows"

#: Deliberately not `fwi_stations_today.parquet`, which belongs to
#: derived_fwi_stations. Both jobs wrote that file until the September 2026
#: audit, so whichever ran last won.
OUTPUT_NAME = "fwi_stations_cwfis.parquet"


#: No server-side bbox. EPSG:4326 is read lat,lon by WFS 2.0, and CRS84 was
#: honoured only loosely here — both returned stations well outside British
#: Columbia (Saskatchewan, and latitudes past 64N). The whole feed is 1,564
#: stations for about 900 KB, so it is fetched entire and filtered on each
#: station's own lat/lon properties, which is exact.
_PARAMS: dict[str, str] = {
    "service": "WFS",
    "version": "2.0.0",
    "request": "GetFeature",
    "typeName": "public:firewx_stns_current",
    "outputFormat": "application/json",
}


def _in_bbox(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    return BBOX_SOUTH <= lat <= BBOX_NORTH and BBOX_WEST <= lon <= BBOX_EAST


class CWFISFWIDailyJob(IngestJob):
    name = "cwfis_fwi_daily"
    cadence = "0 18 * * *"
    label = "NRCan CWFIS · Fire Weather Index daily"

    async def run(self, ctx: IngestContext) -> IngestReport:
        fetched_at = ctx.started_at_utc.isoformat()
        today = ctx.started_at_utc.strftime("%Y-%m-%d")

        fc = None
        try:
            ctx.log.info("cwfis.fetch")
            r = await ctx.client.get(WFS_URL, params=_PARAMS, timeout=60.0)
            r.raise_for_status()
            try:
                fc = r.json()
            except (json.JSONDecodeError, ValueError):
                fc = json.loads(r.text)
        except (httpx.HTTPError, ValueError) as exc:
            # Log the reason. The previous version swallowed it into a blanket
            # "GeoServer unreachable", which hid a renamed layer for months.
            ctx.log.warning("cwfis.fetch_failed", error=str(exc))

        # A failure here is not a platform failure: derived_fwi_stations is the
        # source /api/fwi/today reads, and it depends only on Open-Meteo.
        if fc is None:
            return IngestReport(
                job_name=self.name,
                status="fail",
                error=(
                    "CWFIS WFS returned no usable FeatureCollection. Will retry on "
                    "the next cron; /api/fwi/today is served by derived_fwi_stations "
                    "and is unaffected."
                ),
            )

        features = fc.get("features", []) or []
        # Archive raw
        raw_path = self.raw_path(f"{today}.geojson")
        raw_path.write_text(json.dumps(fc), encoding="utf-8")

        rows: list[dict] = []
        for feat in features:
            props = feat.get("properties", {}) or {}
            geom = feat.get("geometry") or {}
            lat = kvs(props, "lat", "latitude")
            lon = kvs(props, "lon", "longitude")
            if (lat is None or lon is None) and geom.get("type") == "Point":
                coords = geom.get("coordinates") or [None, None]
                lon = coords[0] if lon is None else lon
                lat = coords[1] if lat is None else lat
            try:
                lat_f = float(lat) if lat is not None else None
                lon_f = float(lon) if lon is not None else None
            except (TypeError, ValueError):
                lat_f, lon_f = None, None

            if not _in_bbox(lat_f, lon_f):
                continue

            station_id = kvs(props, "station_id", "wmo", "wmo_code", "stn_id", "id")
            rows.append(
                {
                    "station_id": str(station_id) if station_id is not None else "",
                    "station_name": str(kvs(props, "station_name", "name") or ""),
                    "agency": str(kvs(props, "agency") or ""),
                    "latitude": lat_f,
                    "longitude": lon_f,
                    "observation_date_local": str(
                        kvs(props, "rep_date", "obs_date", "observation_date") or ""
                    ),
                    "temp_c": kvs(props, "temp", "temperature"),
                    "rh_pct": kvs(props, "rh", "relative_humidity"),
                    "wind_kmh": kvs(props, "wind_speed", "ws"),
                    "precip_mm": kvs(props, "precip", "precipitation"),
                    "ffmc": kvs(props, "ffmc"),
                    "dmc": kvs(props, "dmc"),
                    "dc": kvs(props, "dc"),
                    "isi": kvs(props, "isi"),
                    "bui": kvs(props, "bui"),
                    "fwi": kvs(props, "fwi"),
                    "dsr": kvs(props, "dsr"),
                    "fetched_at_utc": fetched_at,
                }
            )

        df = pd.DataFrame(rows)
        today_path = PROCESSED_ROOT / OUTPUT_NAME
        today_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(today_path, compression="zstd", index=False)

        # This used to write `fwi_stations_today.parquet`, the same file
        # derived_fwi rewrites every 30 minutes — so on the one day a year this
        # job succeeded, its rows survived half an hour. Separate files now.
        #
        # An append-only `fwi_stations_history.parquet` was also written here
        # and never read by anything — no router, no model, no test. Removed in
        # the September 2026 audit rather than left to grow unbounded for a
        # reader that never arrived.
        ctx.log.info("cwfis.written", rows=len(df))

        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=len(features),
            rows_written=len(df),
            bytes_written=today_path.stat().st_size,
            artifacts=[raw_path, today_path],
        )
