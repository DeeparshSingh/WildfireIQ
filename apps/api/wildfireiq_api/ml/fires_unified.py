"""Build `data/processed/fires_unified.parquet`.

Concatenates the 1999-2024 historical record (`fires_historical.parquet`)
with the 2025+ active/recent rows (`fires_current.parquet`) into a single
union table, so downstream consumers — model training, the climate
analytics in Phase 6, and a future "what's burned in BC ever?" view —
don't need to know which feed any given row came from.

Idempotent. Re-run via `make fires-unified` or
`uv run python -m wildfireiq_api.ml.fires_unified`.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[4]
PROCESSED = REPO_ROOT / "data" / "processed"

UNIFIED_COLS = [
    "fire_id",
    "fire_year",
    "fire_name",
    "hectares",
    "discovery_date_utc",
    "ignition_cause",
    "latitude",
    "longitude",
    "geom_wkt",
    "geom_kind",
    "source",          # "historical" | "current"
    "status",          # only set for current rows
    "stage_of_control",  # only set for current rows
]


def build() -> Path:
    hist = pd.read_parquet(PROCESSED / "fires_historical.parquet").copy()
    hist["source"] = "historical"
    hist["status"] = None
    hist["stage_of_control"] = None
    if "source_layer" in hist.columns:
        hist = hist.drop(columns=["source_layer"])

    cur = pd.read_parquet(PROCESSED / "fires_current.parquet").copy()
    cur["source"] = "current"
    cur["discovery_date_utc"] = pd.to_datetime(cur["discovery_date_utc"], errors="coerce")
    cur["fire_year"] = cur["discovery_date_utc"].dt.year.astype("Int64")
    cur["ignition_cause"] = None
    if "fetched_at_utc" in cur.columns:
        cur = cur.drop(columns=["fetched_at_utc"])

    for c in UNIFIED_COLS:
        if c not in hist.columns:
            hist[c] = None
        if c not in cur.columns:
            cur[c] = None

    hist = hist[UNIFIED_COLS]
    cur = cur[UNIFIED_COLS]

    # Deduplicate: a fire_id appearing in both feeds → keep the current row
    # (it has live status). Historical rows for that id are dropped.
    cur_ids = set(cur["fire_id"].dropna().astype(str))
    hist = hist[~hist["fire_id"].astype(str).isin(cur_ids)]

    unified = pd.concat([hist, cur], ignore_index=True)
    # Normalise the date column to a single dtype so parquet doesn't choke
    # on a mixed-object column (historical stores ISO strings; current
    # stores Timestamps).
    unified["discovery_date_utc"] = pd.to_datetime(
        unified["discovery_date_utc"], errors="coerce", utc=True
    )
    unified = unified.sort_values(["fire_year", "discovery_date_utc"], na_position="last")

    out = PROCESSED / "fires_unified.parquet"
    unified.to_parquet(out, index=False)
    return out


def _main() -> None:
    p = build()
    n = len(pd.read_parquet(p))
    print(f"wrote {p} with {n} rows")


if __name__ == "__main__":
    _main()
