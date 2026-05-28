"""BC Emergency Management evacuation orders/alerts ingest (every 5 min)."""

from __future__ import annotations

import json

import httpx
import pandas as pd
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry

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
from .base import IngestContext, IngestJob, IngestReport, kvs, parse_iso

CANDIDATE_URLS = [
    "https://services6.arcgis.com/ubm4tcTYICKBpist/arcgis/rest/services/"
    "Evacuation_Orders_and_Alerts/FeatureServer/0/query"
    "?where=1=1&outFields=*&outSR=4326&f=geojson",
    "https://services6.arcgis.com/ubm4tcTYICKBpist/arcgis/rest/services/"
    "Public_Safety_Events/FeatureServer/0/query"
    "?where=1=1&outFields=*&outSR=4326&f=geojson",
]


def _normalize_status(raw: str | None) -> str | None:
    if not raw:
        return None
    s = str(raw).strip().lower()
    if "order" in s:
        return "Order"
    if "alert" in s:
        return "Alert"
    if "rescind" in s or "rescis" in s or "all clear" in s:
        return "Rescind"
    return str(raw)


class BCEMEvacuationJob(IngestJob):
    name = "bcem_evac"
    cadence = "*/5 * * * *"
    label = "BC Emergency Management · evacuation orders/alerts"

    async def run(self, ctx: IngestContext) -> IngestReport:
        fetched_at = ctx.started_at_utc.isoformat()
        stamp = ctx.started_at_utc.strftime("%Y-%m-%dT%H%MZ")
        artifacts: list = []

        gj: dict | None = None
        used_url: str | None = None
        probe_notes: list[str] = []

        for url in CANDIDATE_URLS:
            ctx.log.info("bcem.fetch", url=url)
            try:
                r = await ctx.client.get(url)
            except httpx.HTTPError as e:
                probe_notes.append(f"{url} -> http_err {e!r}")
                continue
            if r.status_code == 404:
                probe_notes.append(f"{url} -> 404")
                continue
            try:
                r.raise_for_status()
                gj = r.json()
                used_url = url
                break
            except Exception as e:
                probe_notes.append(f"{url} -> {e!r}")
                continue

        if gj is None or used_url is None:
            ctx.log.info("bcem.no_endpoint", notes=probe_notes)
            return IngestReport(
                job_name=self.name,
                status="partial",
                note="no BCEM endpoint reachable: " + "; ".join(probe_notes),
            )

        raw_path = self.raw_path(f"{stamp}.geojson")
        raw_path.write_text(json.dumps(gj), encoding="utf-8")
        artifacts.append(raw_path)

        region = box(BBOX_WEST, BBOX_SOUTH, BBOX_EAST, BBOX_NORTH)
        features = gj.get("features", []) or []
        rows = []
        for f in features:
            geom_raw = f.get("geometry")
            if not geom_raw:
                continue
            try:
                geom: BaseGeometry = shape(geom_raw)
            except Exception:
                continue
            if geom.is_empty or not geom.intersects(region):
                continue

            props = f.get("properties") or {}
            # ORDER_ALERT_STATUS is the lifecycle status (Order/Alert/Rescind).
            # EVENT_TYPE is the underlying event nature (Fire/Flood/Landslide).
            # These are SEPARATE fields — the prior parser confused them.
            status = _normalize_status(
                kvs(props, "ORDER_ALERT_STATUS", "STATUS", "OrderAlertStatus", "Status")
            )
            event_type = kvs(props, "EVENT_TYPE", "EventType")
            order_alert_name = kvs(props, "ORDER_ALERT_NAME", "OrderAlertName")
            issued_raw = kvs(
                props,
                "EVENT_START_DATE",
                "DATE_MODIFIED",
                "ISSUED_DATE",
                "IssuedDate",
                "DATE_ISSUED",
                "EVENT_DATE",
                "EventDate",
            )
            # Some ArcGIS feeds give millis since epoch.
            issued_iso: str | None = None
            if isinstance(issued_raw, (int, float)):
                try:
                    issued_iso = pd.to_datetime(issued_raw, unit="ms", utc=True).isoformat()
                except Exception:
                    issued_iso = None
            elif isinstance(issued_raw, str):
                d = parse_iso(issued_raw)
                issued_iso = d.isoformat() if d else issued_raw

            event_id = str(
                kvs(props, "EVENT_ID", "EventID", "OBJECTID", "GLOBALID", "GlobalID")
                or f.get("id", "")
            )
            try:
                area_ha = float(geom.area) * 1e4  # rough: degrees^2 * 1e4 ~ very approximate
            except Exception:
                area_ha = None
            # Prefer explicit field if present
            area_field = kvs(props, "AREA_HECTARES", "Hectares", "Area_ha")
            if area_field is not None:
                try:
                    area_ha = float(area_field)
                except (TypeError, ValueError):
                    pass

            rows.append(
                {
                    "event_id": event_id,
                    "event_name": kvs(props, "EVENT_NAME", "NAME", "Name", "EventName"),
                    "order_alert_name": order_alert_name,
                    "event_type": event_type,
                    "status": status,
                    "issuing_agency": kvs(
                        props, "ISSUING_AGENCY", "IssuingAgency", "AGENCY", "Agency"
                    ),
                    "issued_utc": issued_iso,
                    "area_hectares": area_ha,
                    "geom_wkt": geom.wkt,
                    "fetched_at_utc": fetched_at,
                }
            )

        df = pd.DataFrame(
            rows,
            columns=[
                "event_id",
                "event_name",
                "order_alert_name",
                "event_type",
                "status",
                "issuing_agency",
                "issued_utc",
                "area_hectares",
                "geom_wkt",
                "fetched_at_utc",
            ],
        )

        out_path = PROCESSED_ROOT / "evac_active.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_path, compression="zstd", index=False)
        artifacts.append(out_path)

        ctx.log.info("bcem.written", rows=len(df), endpoint=used_url)

        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=len(features),
            rows_written=len(df),
            bytes_written=out_path.stat().st_size,
            note=f"endpoint={used_url}",
            artifacts=artifacts,
        )
