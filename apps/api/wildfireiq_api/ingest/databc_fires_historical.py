"""DataBC historical wildfire bootstrap (one-time).

Tries the bulk zip download first; on failure falls back to paginated WFS.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC

import pandas as pd
from shapely.geometry import box, shape

from ..constants import BBOX_EAST, BBOX_NORTH, BBOX_SOUTH, BBOX_WEST
from ..paths import PROCESSED_ROOT
from .base import IngestContext, IngestJob, IngestReport, kvs, parse_iso

WFS_BASE = "https://openmaps.gov.bc.ca/geo/pub/wfs"
PERIM_TYPE = "pub:WHSE_LAND_AND_NATURAL_RESOURCE.PROT_HISTORICAL_FIRE_POLYS_SP"
POINT_TYPE = "pub:WHSE_LAND_AND_NATURAL_RESOURCE.PROT_HISTORICAL_INCIDENTS_SP"
PERIM_ZIP_URL = (
    "https://pub.data.gov.bc.ca/datasets/"
    "02dba161-fdb7-48ae-a4bb-bd6ef017c36d/"
    "PROT_HISTORICAL_FIRE_POLYS_SP.zip"
)

PAGE_SIZE = 1000


def _wfs_page_params(type_name: str, start_index: int) -> dict[str, str]:
    return {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": type_name,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "CQL_FILTER": "FIRE_YEAR>=1999",
        "count": str(PAGE_SIZE),
        "startIndex": str(start_index),
    }


def _row_from_feature(feat: dict, layer_label: str, kind: str, bbox_poly) -> dict | None:
    props = feat.get("properties", {}) or {}
    geom = feat.get("geometry")
    wkt = ""
    lat = None
    lon = None
    keep = False
    if geom:
        try:
            g = shape(geom)
            wkt = g.wkt
            c = g.centroid
            lat = float(c.y)
            lon = float(c.x)
            if kind == "polygon":
                keep = g.intersects(bbox_poly)
            else:
                keep = (BBOX_WEST <= lon <= BBOX_EAST) and (BBOX_SOUTH <= lat <= BBOX_NORTH)
        except Exception:
            return None
    if not keep:
        return None

    disc = kvs(
        props,
        "IGNITION_DATE",
        "DISCOVERY_DATE",
        "FIRE_DISCOVERY_DATE",
        "TRACK_DATE",
    )
    disc_dt = parse_iso(disc) if isinstance(disc, str) else None

    hectares_raw = kvs(props, "FIRE_SIZE_HECTARES", "SIZE_HA", "CURRENT_SIZE")

    return {
        "fire_id": str(
            kvs(props, "FIRE_NUMBER", "FIRE_NUM", "FIRE_ID", "OBJECTID") or ""
        ),
        "fire_year": int(kvs(props, "FIRE_YEAR") or 0) or None,
        "fire_name": str(kvs(props, "FIRE_NAME", "INCIDENT_NAME") or ""),
        "hectares": float(hectares_raw) if hectares_raw is not None else None,
        "discovery_date_utc": disc_dt.astimezone(UTC).isoformat() if disc_dt else "",
        "ignition_cause": str(
            kvs(props, "FIRE_CAUSE", "GENERAL_CAUSE", "IGNITION_CAUSE") or ""
        ),
        "latitude": lat,
        "longitude": lon,
        "geom_wkt": wkt,
        "geom_kind": kind,
        "source_layer": layer_label,
    }


async def _wfs_paged(ctx: IngestContext, type_name: str, kind: str, layer_label: str, bbox_poly):
    rows = []
    rows_in = 0
    start = 0
    while True:
        params = _wfs_page_params(type_name, start)
        r = await ctx.client.get(WFS_BASE, params=params)
        r.raise_for_status()
        try:
            fc = r.json()
        except Exception:
            break
        feats = fc.get("features", []) or []
        if not feats:
            break
        rows_in += len(feats)
        for f in feats:
            row = _row_from_feature(f, layer_label, kind, bbox_poly)
            if row:
                rows.append(row)
        ctx.log.info(
            "databc_hist.page",
            layer=layer_label,
            start=start,
            got=len(feats),
            kept=len(rows),
        )
        if len(feats) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return rows, rows_in


async def _try_zip_perimeters(ctx: IngestContext, bbox_poly):
    """Try to fetch the bulk zip; returns (rows, rows_in) or raises."""
    ctx.log.info("databc_hist.zip.fetch")
    r = await ctx.client.get(PERIM_ZIP_URL, timeout=120.0)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    # Look for any .geojson or .json inside; otherwise we'd need a shapefile reader
    # (geopandas not in deps), so we only handle GeoJSON-bearing zips.
    candidates = [n for n in z.namelist() if n.lower().endswith((".geojson", ".json"))]
    if not candidates:
        raise RuntimeError("zip contains no geojson; falling back to WFS")
    rows = []
    rows_in = 0
    for name in candidates:
        data = z.read(name)
        fc = json.loads(data)
        feats = fc.get("features", []) or []
        rows_in += len(feats)
        for f in feats:
            row = _row_from_feature(f, "historical_perimeters_zip", "polygon", bbox_poly)
            if row:
                rows.append(row)
    return rows, rows_in


class DataBCFiresHistoricalJob(IngestJob):
    name = "databc_fires_historical"
    cadence = None
    label = "BC Wildfire Service · historical fires (bootstrap)"

    async def run(self, ctx: IngestContext) -> IngestReport:
        bbox_poly = box(BBOX_WEST, BBOX_SOUTH, BBOX_EAST, BBOX_NORTH)
        notes: list[str] = []

        # Perimeters: try zip → fallback to WFS
        try:
            perim_rows, perim_in = await _try_zip_perimeters(ctx, bbox_poly)
            ctx.log.info("databc_hist.zip.ok", rows=len(perim_rows))
        except Exception as e:
            notes.append(f"perimeters zip failed ({type(e).__name__}); used WFS pagination")
            ctx.log.info("databc_hist.zip.fail", err=str(e))
            perim_rows, perim_in = await _wfs_paged(
                ctx, PERIM_TYPE, "polygon", "historical_perimeters_wfs", bbox_poly
            )

        # Points: WFS paginated
        point_rows, point_in = await _wfs_paged(
            ctx, POINT_TYPE, "point", "historical_incidents_wfs", bbox_poly
        )

        all_rows = perim_rows + point_rows
        df = pd.DataFrame(all_rows)
        if not df.empty:
            df = df.sort_values("discovery_date_utc", kind="stable").reset_index(drop=True)

        out_path = PROCESSED_ROOT / "fires_historical.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_path, compression="zstd", index=False)

        notes.append(
            "current-year fires not included (live layer covers them)"
        )

        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=perim_in + point_in,
            rows_written=len(df),
            bytes_written=out_path.stat().st_size,
            note="; ".join(notes),
            artifacts=[out_path],
        )
