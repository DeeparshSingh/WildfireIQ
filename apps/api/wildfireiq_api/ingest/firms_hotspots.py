"""NASA FIRMS satellite hotspots ingest (every 30 min)."""

from __future__ import annotations

import io
from datetime import datetime, timezone

import pandas as pd

from ..constants import (
    BC_BBOX_EAST as BBOX_EAST,
    BC_BBOX_NORTH as BBOX_NORTH,
    BC_BBOX_SOUTH as BBOX_SOUTH,
    BC_BBOX_WEST as BBOX_WEST,
)
from ..paths import PROCESSED_ROOT
from ..settings import get_settings
from .base import IngestContext, IngestJob, IngestReport


FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/usfs/api/area/csv"
SOURCES = ["VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT", "MODIS_NRT"]

MODIS_CONF_MAP = {"l": 20, "n": 60, "h": 90, "L": 20, "N": 60, "H": 90}


def _short_source(s: str) -> str:
    return s.replace("_NRT", "")


class FIRMSHotspotsJob(IngestJob):
    name = "firms_hotspots"
    cadence = "*/30 * * * *"
    label = "NASA FIRMS · satellite hotspots"

    async def run(self, ctx: IngestContext) -> IngestReport:
        key = get_settings().firms_map_key
        if not key:
            return IngestReport(
                job_name=self.name,
                status="fail",
                error="FIRMS_MAP_KEY not configured",
            )

        bbox = f"{BBOX_WEST},{BBOX_SOUTH},{BBOX_EAST},{BBOX_NORTH}"
        day = ctx.started_at_utc.strftime("%Y-%m-%d")
        fetched_at = ctx.started_at_utc.isoformat()
        artifacts: list = []

        all_frames: list[pd.DataFrame] = []
        rows_in_total = 0

        for source in SOURCES:
            # 3-day window — FIRMS NRT USFS endpoint caps at 3 days per request.
            # Phase 4 will stitch multiple days for a longer historical view.
            url = f"{FIRMS_BASE}/{key}/{source}/{bbox}/3"
            ctx.log.info("firms.fetch", source=source)
            r = await ctx.client.get(url)
            r.raise_for_status()
            csv_text = r.text

            raw_path = self.raw_path(day, f"{source}.csv")
            raw_path.write_text(csv_text, encoding="utf-8")
            artifacts.append(raw_path)

            try:
                df = pd.read_csv(io.StringIO(csv_text))
            except Exception as e:  # noqa: BLE001
                ctx.log.info("firms.parse_failed", source=source, err=str(e))
                continue

            if df.empty:
                ctx.log.info("firms.empty", source=source)
                continue

            rows_in_total += len(df)

            # Normalize confidence
            if "confidence" not in df.columns:
                df["confidence"] = None
            if source == "MODIS_NRT":
                # MODIS confidence may already be numeric 0-100, or l/n/h
                def _conv(v):
                    if isinstance(v, str) and v.strip() in MODIS_CONF_MAP:
                        return MODIS_CONF_MAP[v.strip()]
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return None

                df["confidence"] = df["confidence"].map(_conv)
            else:
                df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")

            df = df[df["confidence"].fillna(-1) >= 30].copy()

            if df.empty:
                continue

            # Combine date + time
            acq_date = df.get("acq_date", pd.Series([""] * len(df))).astype(str)
            acq_time = df.get("acq_time", pd.Series([0] * len(df)))
            # acq_time is HHMM as int/str (zero-padded). Make it 4 chars.
            acq_time_s = acq_time.apply(
                lambda v: str(int(v)).zfill(4) if pd.notna(v) and str(v) != "" else "0000"
            )
            dt = pd.to_datetime(
                acq_date + " " + acq_time_s.str[:2] + ":" + acq_time_s.str[2:4] + ":00",
                utc=True,
                errors="coerce",
            )

            out = pd.DataFrame(
                {
                    "latitude": pd.to_numeric(df.get("latitude"), errors="coerce"),
                    "longitude": pd.to_numeric(df.get("longitude"), errors="coerce"),
                    "acq_datetime_utc": dt.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "brightness": pd.to_numeric(
                        df.get("bright_ti4", df.get("brightness")), errors="coerce"
                    ),
                    "frp": pd.to_numeric(df.get("frp"), errors="coerce"),
                    "confidence": df["confidence"].astype(float),
                    "source": _short_source(source),
                    "daynight": df.get("daynight", pd.Series([""] * len(df))).astype(str),
                    "satellite": df.get("satellite", pd.Series([""] * len(df))).astype(str),
                    "fetched_at_utc": fetched_at,
                }
            )
            all_frames.append(out)
            ctx.log.info("firms.kept", source=source, rows=len(out))

        if all_frames:
            merged = pd.concat(all_frames, ignore_index=True)
        else:
            merged = pd.DataFrame(
                columns=[
                    "latitude",
                    "longitude",
                    "acq_datetime_utc",
                    "brightness",
                    "frp",
                    "confidence",
                    "source",
                    "daynight",
                    "satellite",
                    "fetched_at_utc",
                ]
            )

        out_path = PROCESSED_ROOT / "firms_hotspots_recent.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_parquet(out_path, compression="zstd", index=False)
        artifacts.append(out_path)

        ctx.log.info("firms.written", rows=len(merged), path=str(out_path))

        return IngestReport(
            job_name=self.name,
            status="ok",
            rows_in=rows_in_total,
            rows_written=len(merged),
            bytes_written=out_path.stat().st_size,
            artifacts=artifacts,
        )
