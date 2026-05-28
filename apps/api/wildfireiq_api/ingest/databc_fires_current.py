"""DataBC current wildfire perimeters + points ingest (every 15 min)."""

from __future__ import annotations

import json
from datetime import UTC

import pandas as pd
from shapely.geometry import shape

from ..constants import (
    BC_BBOX_EAST,
    BC_BBOX_NORTH,
    BC_BBOX_SOUTH,
    BC_BBOX_WEST,
)
from ..paths import PROCESSED_ROOT
from .base import IngestContext, IngestJob, IngestReport, kvs, parse_iso

WFS_BASE = "https://openmaps.gov.bc.ca/geo/pub/wfs"
PERIM_TYPE = "pub:WHSE_LAND_AND_NATURAL_RESOURCE.PROT_CURRENT_FIRE_POLYS_SP"
POINT_TYPE = "pub:WHSE_LAND_AND_NATURAL_RESOURCE.PROT_CURRENT_FIRE_PNTS_SP"


def _wfs_params(type_name: str) -> dict[str, str]:
    return {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": type_name,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        # Province-wide query so the layer shows the same ~13 active fires
        # BC Wildfire Service displays, not just the Thompson-Okanagan subset.
        "BBOX": f"{BC_BBOX_WEST},{BC_BBOX_SOUTH},{BC_BBOX_EAST},{BC_BBOX_NORTH},EPSG:4326",
    }


class DataBCFiresCurrentJob(IngestJob):
    name = "databc_fires_current"
    cadence = "*/15 * * * *"
    label = "BC Wildfire Service · current fires"

    async def run(self, ctx: IngestContext) -> IngestReport:
        stamp = ctx.started_at_utc.strftime("%Y-%m-%dT%H%MZ")
        fetched_at = ctx.started_at_utc.isoformat()
        artifacts: list = []

        rows: list[dict] = []
        rows_in_total = 0

        for kind, type_name, fname in (
            ("polygon", PERIM_TYPE, "perimeters.geojson"),
            ("point", POINT_TYPE, "points.geojson"),
        ):
            ctx.log.info("databc.fetch", layer=kind)
            r = await ctx.client.get(WFS_BASE, params=_wfs_params(type_name))
            r.raise_for_status()
            text_body = r.text
            raw_path = self.raw_path(stamp, fname)
            raw_path.write_text(text_body, encoding="utf-8")
            artifacts.append(raw_path)

            try:
                fc = json.loads(text_body)
            except json.JSONDecodeError:
                ctx.log.info("databc.parse_failed", layer=kind)
                continue
            features = fc.get("features", []) or []
            rows_in_total += len(features)
            ctx.log.info("databc.fetched", layer=kind, n_features=len(features))

            for feat in features:
                props = feat.get("properties", {}) or {}
                geom = feat.get("geometry")
                wkt = ""
                lat = None
                lon = None
                if geom:
                    try:
                        g = shape(geom)
                        wkt = g.wkt
                        c = g.centroid
                        lat = float(c.y)
                        lon = float(c.x)
                    except Exception:
                        pass

                disc = kvs(
                    props,
                    "DISCOVERY_DATE",
                    "IGNITION_DATE",
                    "FIRE_DISCOVERY_DATE",
                    "TRACK_DATE",
                )
                disc_dt = parse_iso(disc) if isinstance(disc, str) else None

                rows.append(
                    {
                        "fire_id": str(
                            kvs(props, "FIRE_NUMBER", "FIRE_NUM", "FIRE_ID", "OBJECTID") or ""
                        ),
                        "fire_name": str(kvs(props, "FIRE_NAME", "INCIDENT_NAME") or ""),
                        "status": str(kvs(props, "FIRE_STATUS", "STATUS") or ""),
                        "stage_of_control": str(
                            kvs(props, "STAGE_OF_CONTROL", "STAGE_OF_CONTROL_DESC") or ""
                        ),
                        "hectares": float(
                            kvs(props, "CURRENT_SIZE", "FIRE_SIZE_HECTARES", "SIZE_HA") or 0.0
                        )
                        if kvs(props, "CURRENT_SIZE", "FIRE_SIZE_HECTARES", "SIZE_HA")
                        is not None
                        else None,
                        "discovery_date_utc": disc_dt.astimezone(UTC).isoformat()
                        if disc_dt
                        else "",
                        "latitude": lat,
                        "longitude": lon,
                        "geom_wkt": wkt,
                        "geom_kind": kind,
                        "fetched_at_utc": fetched_at,
                    }
                )

        df = pd.DataFrame(rows)
        out_path = PROCESSED_ROOT / "fires_current.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_path, compression="zstd", index=False)
        artifacts.append(out_path)

        ctx.log.info("databc.written", rows=len(df), path=str(out_path))

        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=rows_in_total,
            rows_written=len(df),
            bytes_written=out_path.stat().st_size,
            artifacts=artifacts,
        )
