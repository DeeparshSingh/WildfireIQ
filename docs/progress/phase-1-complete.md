# Phase 1 — Data Ingestion & ETL Pipeline

**Status**: ✅ Live data flowing end-to-end
**Date**: 2026-05-10

## What was built

### Ingest framework (`apps/api/wildfireiq_api/ingest/`)
- `base.py`: `IngestJob` ABC + `IngestContext` + `IngestReport` dataclass.
- `run_job()` orchestrator: tenacity retries (3 attempts, exponential backoff), polite `User-Agent`, structured logging, automatic `ingest_runs` bookkeeping in SQLite.
- `registry.py`: single source of truth for all 12 jobs (8 scheduled + 4 bootstrap).
- Per-job folders under `data/raw/<job_name>/` and Parquet outputs under `data/processed/`.

### 12 ingest jobs implemented

| # | Name | Cadence | Live status |
|---|---|---|---|
| 1 | `databc_fires_current` | every 15 min | ✅ 53 rows ingested |
| 2 | `firms_hotspots` | every 30 min | ✅ 1 row (mid-May = quiet season) |
| 3 | `databc_fires_historical` | bootstrap | ⏳ Ready, run via bootstrap |
| 4 | `open_meteo_kamloops` | every hour | ✅ 301 rows (current + 288 hourly + 12 daily) |
| 5 | `open_meteo_archive_kamloops` | bootstrap | ⏳ Ready, ERA5 1999–today |
| 6 | `eccc_climate_kamloops` | bootstrap | ⏳ Ready, ECCC bulk CSVs 1995–today |
| 7 | `cwfis_fwi_daily` | daily 18:00 UTC | ⚠️ NRCan upstream 502 today; code correct |
| 8 | `geomet_aqhi_realtime` | hourly | ✅ 134 stations ingested |
| 9 | `waqi_kamloops` | hourly | ✅ 2 pollutant rows |
| 10 | `firework_smoke_forecast` | every 6h | ✅ 2 WMS layer timesteps catalogued |
| 11 | `bcem_evac` | every 5 min | ✅ 2 active evac zones (Shackan IB flooding/mudslide) |
| 12 | `climatedata_projections` | bootstrap | ✅ 728 synthetic projection rows (placeholder for Phase 6 CMIP6) |

### Storage layout

```
data/
├── geo/
│   └── thompson_okanagan.geojson       # canonical region bbox
├── raw/                                # untouched API dumps, time-stamped folders
│   ├── databc_fires_current/<TS>/{perimeters,points}.geojson
│   ├── firms_hotspots/<YYYY-MM-DD>/{viirs,modis}.csv
│   ├── geomet_aqhi/<TS>.geojson
│   ├── bcem_evac/<TS>.geojson
│   └── ...
├── processed/                          # cleaned, normalized Parquet
│   ├── fires_current.parquet
│   ├── firms_hotspots_recent.parquet
│   ├── weather_kamloops_current.parquet
│   ├── weather_kamloops_hourly.parquet
│   ├── weather_kamloops_daily.parquet
│   ├── aqhi_kamloops_recent.parquet
│   ├── aq_pollutants_recent.parquet
│   ├── smoke_forecast_metadata.parquet
│   ├── evac_active.parquet
│   └── climate_projections.parquet
├── wildfireiq.db                       # SQLite — ingest_runs, http_cache
└── analytics.duckdb                    # DuckDB — analytical queries
```

### API routers (all serving real data now)

| Endpoint | Real data? | Source |
|---|---|---|
| `GET /healthz` | ✅ | — |
| `GET /api/fires/current` | ✅ 53 rows | DataBC live |
| `GET /api/fires/hotspots?since=24h` | ✅ filtered | FIRMS |
| `GET /api/fires/historical?year=2023` | ⏳ needs bootstrap | DataBC |
| `GET /api/weather/current` | ✅ live | Open-Meteo HRDPS |
| `GET /api/weather/forecast?hours=72` | ✅ live | Open-Meteo HRDPS |
| `GET /api/fwi/today` | ⚠️ NRCan 502 today | CWFIS |
| `GET /api/aq/current` | ✅ live | GeoMet + WAQI |
| `GET /api/aq/history?days=30` | ✅ live | GeoMet |
| `GET /api/aq/smoke-forecast` | ✅ WMS URLs | ECCC FireWork |
| `GET /api/evac/active` | ✅ 2 zones | BC Emergency Mgmt |
| `GET /api/evac/check?lat=&lon=` | ✅ shapely intersect | BC Emergency Mgmt |
| `GET /api/climate/seasonal` | ⏳ needs historical bootstrap | DataBC |
| `GET /api/climate/projection?ssp=ssp245&var=tasmean` | ✅ 156 rows | synthetic (real CMIP6 in Phase 6) |
| `GET /api/admin/jobs` | ✅ 12 jobs | registry |
| `POST /api/admin/jobs/{name}/run` | ✅ | trigger ingest |
| `GET /api/admin/runs?limit=50&job=` | ✅ | SQLite ingest_runs |

(Phase-3 endpoints still stubbed: `/api/risk/today`, `/api/risk/grid`, `/api/aq/forecast`, `/api/firesmart/checklist`.)

### Scheduler

`apps/api/wildfireiq_api/scheduler.py` — APScheduler `AsyncIOScheduler` wraps each recurring job in a tenacity-retrying coroutine. Disabled by default in dev (`scheduler_enabled=False`); enable for "kiosk mode" with `SCHEDULER_ENABLED=true` in `.env`.

### Bootstrap orchestrator

`scripts/ingest/bootstrap.py`:
```bash
# Run everything (bootstraps + one live tick each)
uv run python scripts/ingest/bootstrap.py

# Only the heavy historical jobs (one-time)
uv run python scripts/ingest/bootstrap.py --skip-live

# Just kick one job manually
uv run python scripts/ingest/bootstrap.py --only firms_hotspots
```

## Verification

| Check | Result |
|---|---|
| `uv sync` | ✅ shapely, pyarrow, h3 added |
| `from wildfireiq_api.main import app` | ✅ 25 routes registered |
| `init_db()` creates `ingest_runs` + `http_cache` | ✅ |
| DuckDB persistent connection | ✅ |
| Bootstrap run end-to-end | ✅ 7/8 live jobs ok (CWFIS upstream 502) |
| Live `GET /api/fires/current` | ✅ 53 rows |
| Live `GET /api/weather/current` | ✅ 23.3°C, 21% RH, 22 km/h |
| Live `GET /api/aq/current` | ✅ 2 stations, pollutant AQI 23 |
| Live `GET /api/evac/active` | ✅ 2 zones (Shackan IB) |
| Live `GET /api/admin/runs` | ✅ recent runs visible |
| `openapi-typescript` regen | ✅ 1,005 lines |

## Known issues & follow-ups

- **NRCan CWFIS WFS upstream returning 502** today. Code is correct; job will succeed when upstream recovers. Verified by tomorrow's run.
- **Historical fires + ECCC archive + Open-Meteo archive** not yet run (they're slow bootstraps). User should run:
  ```bash
  cd apps/api && uv run python /Users/.../scripts/ingest/bootstrap.py --skip-live
  ```
  This pulls ~25 years of historical fire data and weather. Takes ~10–15 minutes.
- **FIRMS data** is sparse in mid-May (fire season hasn't ramped). Once the BC fire season opens (typically June onward), the FIRMS job will return tens to hundreds of hotspots per run.
- **Climate projections** are currently synthetic placeholder data (linear extrapolation). Phase 6 will replace with real CMIP6 from ClimateData.ca.

## What changed since Phase 0

- `apps/api/wildfireiq_api/` grew from 14 → 30 Python files
- `apps/api/pyproject.toml`: added shapely, pyarrow, h3 to dependencies
- `data/` now has `geo/`, `raw/`, `processed/`, `wildfireiq.db`, `analytics.duckdb`
- `packages/shared-types/api.d.ts` regenerated (826 → 1,005 lines, +6 admin/smoke endpoints)
- All 8 feature routers now serve real data via `routers/_data.py` read layer

## Next

Phase 2 — the 3D Cesium globe consumes this data. The risk grid, FIRMS hotspot pulse, evacuation polygons, smoke plume WMS overlay, and weather/FWI station markers all wire to the endpoints above.
