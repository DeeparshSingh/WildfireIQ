"""ECCC GeoMet AQHI realtime ingest (hourly @ :10).

Covers the whole province so the air-quality stations map shows every BC
AQHI station, matching the province-wide fire/hotspot/evac layers. The
/api/aq/current headline still selects the Kamloops station.
"""

from __future__ import annotations

import json

import pandas as pd

from ..constants import BC_BBOX_EAST, BC_BBOX_NORTH, BC_BBOX_SOUTH, BC_BBOX_WEST
from ..paths import PROCESSED_ROOT
from .base import IngestContext, IngestJob, IngestReport, parse_iso

GEOMET_URL = (
    "https://api.weather.gc.ca/collections/aqhi-observations-realtime/items"
    f"?bbox={BC_BBOX_WEST},{BC_BBOX_SOUTH},{BC_BBOX_EAST},{BC_BBOX_NORTH}"
    "&f=json&limit=1000&sortby=-observation_datetime"
)


class GeoMetAQHIRealtimeJob(IngestJob):
    name = "geomet_aqhi_realtime"
    cadence = "10 * * * *"
    label = "ECCC GeoMet · AQHI realtime"

    async def run(self, ctx: IngestContext) -> IngestReport:
        fetched_at = ctx.started_at_utc.isoformat()
        stamp = ctx.started_at_utc.strftime("%Y-%m-%dT%H%MZ")
        artifacts: list = []

        ctx.log.info("geomet_aqhi.fetch")
        r = await ctx.client.get(GEOMET_URL)
        r.raise_for_status()
        gj = r.json()

        raw_path = self.raw_path(f"{stamp}.geojson")
        raw_path.write_text(json.dumps(gj), encoding="utf-8")
        artifacts.append(raw_path)

        features = gj.get("features", []) or []
        rows = []
        for f in features:
            props = f.get("properties") or {}
            geom = f.get("geometry") or {}
            coords = geom.get("coordinates") or [None, None]
            lon, lat = coords[0], coords[1]
            if lat is None or lon is None:
                continue
            obs_dt = parse_iso(props.get("observation_datetime"))
            obs_iso = obs_dt.isoformat() if obs_dt else props.get("observation_datetime")
            rows.append(
                {
                    "station_id": str(
                        props.get("aqhi_station_id")
                        or props.get("location_id")
                        or props.get("id")
                        or f.get("id", "")
                    ),
                    "station_name": props.get("aqhi_station_name")
                    or props.get("location_name_en"),
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "aqhi": pd.to_numeric(props.get("aqhi"), errors="coerce"),
                    "observation_datetime_utc": obs_iso,
                    "fetched_at_utc": fetched_at,
                }
            )

        new_df = pd.DataFrame(
            rows,
            columns=[
                "station_id",
                "station_name",
                "latitude",
                "longitude",
                "aqhi",
                "observation_datetime_utc",
                "fetched_at_utc",
            ],
        )

        out_path = PROCESSED_ROOT / "aqhi_kamloops_recent.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if out_path.exists():
            try:
                existing = pd.read_parquet(out_path)
                merged = pd.concat([existing, new_df], ignore_index=True)
            except Exception as e:
                ctx.log.info("geomet_aqhi.existing_read_fail", err=str(e))
                merged = new_df
        else:
            merged = new_df

        merged = merged.drop_duplicates(
            subset=["station_id", "observation_datetime_utc"]
        ).reset_index(drop=True)

        # Retain last 7 days
        if not merged.empty and "observation_datetime_utc" in merged.columns:
            ts = pd.to_datetime(merged["observation_datetime_utc"], utc=True, errors="coerce")
            cutoff = ctx.started_at_utc - pd.Timedelta(days=7)
            mask = ts.isna() | (ts >= cutoff)
            merged = merged[mask].reset_index(drop=True)

        merged.to_parquet(out_path, compression="zstd", index=False)
        artifacts.append(out_path)

        ctx.log.info("geomet_aqhi.written", rows=len(merged), new=len(new_df))

        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=len(features),
            rows_written=len(merged),
            bytes_written=out_path.stat().st_size,
            artifacts=artifacts,
        )
