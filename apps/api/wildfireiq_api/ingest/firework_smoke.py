"""ECCC FireWork PM2.5 smoke-forecast metadata ingest (every 6h).

Phase 1: scrape the MSC GeoMet WMS GetCapabilities for the
RAQDPS-FW.SFC_PM2.5 layer's available timesteps and emit ready-to-use
GetMap URLs for the frontend. Decoding GRIB2 deferred to Phase 4.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta

import pandas as pd

from ..constants import BC_BBOX_EAST, BC_BBOX_NORTH, BC_BBOX_SOUTH, BC_BBOX_WEST
from ..paths import PROCESSED_ROOT
from .base import IngestContext, IngestJob, IngestReport

# ISO 8601 duration parsing — minimal subset covering ECCC's PT<H>H / PT<M>M / P<D>D / PT<H>H<M>M.
_DUR_RE = re.compile(
    r"^P(?:(?P<d>\d+)D)?(?:T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?)?$"
)


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _parse_iso8601_duration(s: str) -> timedelta | None:
    m = _DUR_RE.match(s.strip())
    if not m:
        return None
    parts = {k: int(v) for k, v in m.groupdict(default="0").items()}
    return timedelta(
        days=parts["d"],
        hours=parts["h"],
        minutes=parts["m"],
        seconds=parts["s"],
    )


CAPS_URL = (
    "https://geo.weather.gc.ca/geomet"
    "?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0"
)
# Spec called for "RAQDPS-FW.SFC_PM2.5"; that exact name is not currently
# advertised by GeoMet. We probe several plausible names in priority order —
# the FireWork wildfire-smoke surface PM2.5 product moves around between
# seasons. Update this list as ECCC renames things.
LAYER_CANDIDATES = [
    "RAQDPS-FW.SFC_PM2.5",
    "RAQDPS.Sfc_PM2.5-WildfireSmokePlume",
    "RAQDPS.SFC_PM2.5",
    "RDAQA-FW_10km_PM2.5",
]


def _getmap_url(layer: str, iso_time: str) -> str:
    # Province-wide BC extent so the smoke overlay covers everywhere the
    # fire/hotspot/evac layers do. WIDTH:HEIGHT ~= the bbox aspect ratio
    # (25° lon × 11.7° lat ≈ 2.1:1) so the PNG isn't stretched. The
    # SingleTileImageryProvider maps this image onto a matching Cesium
    # rectangle (see SmokeLayer.SMOKE_RECT) — the two extents must agree.
    return (
        "https://geo.weather.gc.ca/geomet"
        "?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap"
        f"&LAYERS={layer}&CRS=EPSG:4326"
        f"&BBOX={BC_BBOX_SOUTH},{BC_BBOX_WEST},{BC_BBOX_NORTH},{BC_BBOX_EAST}"
        "&WIDTH=1100&HEIGHT=512&FORMAT=image/png"
        f"&TIME={iso_time}&TRANSPARENT=TRUE"
    )


def _slice_layer_xml(xml_text: str, layer_name: str) -> str | None:
    """Find the <Layer> ... </Layer> block whose <Name> equals layer_name."""
    # Find an occurrence of the layer name in a <Name> tag.
    needle = f"<Name>{layer_name}</Name>"
    idx = xml_text.find(needle)
    if idx < 0:
        return None
    # Walk backward to the enclosing <Layer ...> open tag.
    start = xml_text.rfind("<Layer", 0, idx)
    if start < 0:
        return None
    # Walk forward to the matching </Layer>. Naive depth counter starting at 1.
    depth = 1
    pos = xml_text.find(">", start) + 1
    while pos < len(xml_text) and depth > 0:
        nxt_open = xml_text.find("<Layer", pos)
        nxt_close = xml_text.find("</Layer>", pos)
        if nxt_close < 0:
            return None
        if 0 <= nxt_open < nxt_close:
            depth += 1
            pos = xml_text.find(">", nxt_open) + 1
        else:
            depth -= 1
            pos = nxt_close + len("</Layer>")
    return xml_text[start:pos]


class FireWorkSmokeForecastJob(IngestJob):
    name = "firework_smoke_forecast"
    cadence = "0 */6 * * *"
    label = "ECCC · FireWork PM2.5 smoke forecast"

    async def run(self, ctx: IngestContext) -> IngestReport:
        fetched_at = ctx.started_at_utc.isoformat()
        ctx.log.info("firework.fetch_caps")

        # Stream-read to handle very large XML responses.
        chunks: list[str] = []
        async with ctx.client.stream("GET", CAPS_URL) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_text():
                chunks.append(chunk)
        xml_text = "".join(chunks)
        ctx.log.info("firework.caps_bytes", bytes=len(xml_text))

        layer_xml: str | None = None
        layer_used: str | None = None
        for cand in LAYER_CANDIDATES:
            layer_xml = _slice_layer_xml(xml_text, cand)
            if layer_xml:
                layer_used = cand
                break
        if not layer_xml or not layer_used:
            return IngestReport(
                job_name=self.name,
                status="partial",
                note=f"no candidate FireWork PM2.5 layer found: {LAYER_CANDIDATES}",
            )

        # Parse only the small slice we care about.
        # Strip XML namespaces by hand for robust parsing.
        try:
            root = ET.fromstring(layer_xml)
        except ET.ParseError as e:
            return IngestReport(
                job_name=self.name,
                status="partial",
                note=f"layer xml parse failed: {e}",
            )

        # Find Dimension name="time" — handle either namespaced or not.
        time_text: str | None = None
        for el in root.iter():
            tag = el.tag.rsplit("}", 1)[-1]
            if tag == "Dimension" and el.attrib.get("name") == "time":
                time_text = (el.text or "").strip()
                break

        if not time_text:
            return IngestReport(
                job_name=self.name,
                status="partial",
                note="time dimension not found",
            )

        # Time dimension may be comma-separated list or an interval
        # (start/end/period). ECCC FireWork uses interval form, e.g.
        # `2026-05-13T12:00:00Z/2026-05-16T12:00:00Z/PT3H`. We must expand
        # it into every individual timestep so the scrubber can step through
        # the 48-hour forecast hour-by-hour, not just jump endpoint-to-endpoint.
        timesteps: list[str] = []
        for part in time_text.split(","):
            part = part.strip()
            if not part:
                continue
            if "/" in part:
                bits = [b for b in part.split("/") if b]
                if len(bits) >= 3:
                    start = _parse_iso(bits[0])
                    end = _parse_iso(bits[1])
                    step = _parse_iso8601_duration(bits[2])
                    if start and end and step:
                        cur = start
                        # Safety cap so a runaway interval doesn't explode.
                        for _ in range(256):
                            if cur > end:
                                break
                            timesteps.append(
                                cur.strftime("%Y-%m-%dT%H:%M:%SZ")
                            )
                            cur = cur + step
                        continue
                # Fallback: just keep endpoints if we can't parse period.
                if bits:
                    timesteps.append(bits[0])
                    if len(bits) >= 2:
                        timesteps.append(bits[1])
            else:
                timesteps.append(part)

        rows = [
            {
                "layer_name": layer_used,
                "valid_time_utc": ts,
                "fetch_url": _getmap_url(layer_used, ts),
                "fetched_at_utc": fetched_at,
            }
            for ts in timesteps
        ]
        df = pd.DataFrame(
            rows,
            columns=["layer_name", "valid_time_utc", "fetch_url", "fetched_at_utc"],
        )

        out_path = PROCESSED_ROOT / "smoke_forecast_metadata.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_path, compression="zstd", index=False)

        ctx.log.info("firework.written", rows=len(df))

        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=len(timesteps),
            rows_written=len(df),
            bytes_written=out_path.stat().st_size,
            artifacts=[out_path],
        )
