"""NRCan CWFIS Fire Weather Index daily ingest."""

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


def _params(bbox: bool) -> dict[str, str]:
    p = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": "public:fwi_stns_current",
        "outputFormat": "application/json",
    }
    if bbox:
        p["bbox"] = f"{BBOX_WEST},{BBOX_SOUTH},{BBOX_EAST},{BBOX_NORTH},EPSG:4326"
    return p


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

        # Try bbox first, fall back to full + client filter.
        fc = None
        filter_client = False
        for use_bbox in (True, False):
            try:
                ctx.log.info("cwfis.fetch", bbox=use_bbox)
                r = await ctx.client.get(WFS_URL, params=_params(use_bbox), timeout=60.0)
                r.raise_for_status()
                try:
                    fc = r.json()
                except (json.JSONDecodeError, ValueError):
                    fc = json.loads(r.text)
                filter_client = not use_bbox
                break
            except (httpx.HTTPError, ValueError) as exc:
                ctx.log.info("cwfis.fetch_failed", bbox=use_bbox, error=str(exc))
                fc = None
                continue

        # NRCan's CWFIS GeoServer goes down with 502 errors regularly. Their
        # flat-file datamart at /data/fwi/ now returns HTML wrappers instead
        # of CSVs. Phase 3 will replace this dependency entirely by computing
        # FWI from Open-Meteo weather data with the cffdrs-py port.
        if fc is None:
            return IngestReport(
                job_name=self.name,
                status="fail",
                error="CWFIS GeoServer unreachable (HTTP 502). Will retry on next cron; Phase 3 replaces with derived FWI from Open-Meteo.",
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

            if filter_client and not _in_bbox(lat_f, lon_f):
                continue

            station_id = kvs(props, "station_id", "wmo_code", "stn_id", "id")
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
        today_path = PROCESSED_ROOT / "fwi_stations_today.parquet"
        today_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(today_path, compression="zstd", index=False)

        # Append-only history with dedupe on (station_id, observation_date_local)
        hist_path = PROCESSED_ROOT / "fwi_stations_history.parquet"
        if hist_path.exists():
            try:
                prev = pd.read_parquet(hist_path)
                combined = pd.concat([prev, df], ignore_index=True)
            except Exception:
                combined = df.copy()
        else:
            combined = df.copy()
        if not combined.empty:
            combined = combined.drop_duplicates(
                subset=["station_id", "observation_date_local"], keep="last"
            )
        combined.to_parquet(hist_path, compression="zstd", index=False)

        ctx.log.info("cwfis.written", rows=len(df), history_rows=len(combined))

        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=len(features),
            rows_written=len(df),
            bytes_written=today_path.stat().st_size + hist_path.stat().st_size,
            artifacts=[raw_path, today_path, hist_path],
        )
