# Architecture

A single-page summary of how WildfireIQ Kamloops is wired end-to-end, written for someone who's never opened the repo.

---

## Two halves

### Frontend (`apps/web`)
React 18 + TypeScript on Vite, deployed as a static bundle. The 3D globe is eager (it's the front door); every other route — `/air-quality`, `/preparedness`, `/preparedness/shared`, `/climate`, `/about` — is `React.lazy`-loaded so the initial JS payload stays under 70 KB gzipped (excluding Cesium).

Layout:

```
apps/web/src/
├── app.tsx                  # route table + lazy splits
├── shell/                   # AppShell, Splash, RouteLoader
├── stores/                  # Zustand stores (layers, filters, smoke, globe)
├── lib/api/                 # apiGet client + TanStack Query hooks
└── features/
    ├── globe/               # Cesium viewer, layers, presets, modal
    ├── air-quality/         # AqhiDial, ForecastChart, …
    ├── preparedness/        # Wizard, Checklist, ProgressPanel, …
    └── climate/             # 6 scrollytelling sections + InfoChip
```

### Backend (`apps/api`)
FastAPI on Python 3.12 inside a uv workspace. APScheduler runs 16 ingest jobs on cron cadences. SQLAlchemy + aiosqlite for ops state (`ingest_runs` log). DuckDB for analytics. Parquet (zstd-compressed) for every cached upstream batch.

Layout:

```
apps/api/wildfireiq_api/
├── main.py                  # FastAPI app, lifespan, middleware
├── settings.py              # pydantic-settings
├── db.py                    # SQLAlchemy engine + session_scope
├── scheduler.py             # APScheduler + refresh_stale_jobs()
├── ingest/                  # 16 IngestJob subclasses + registry.py
├── routers/                 # 1 router per domain
├── ml/                      # FWI port, trainers, inference, ONNX export
└── tests/                   # pytest — 47 tests
```

### Data (`data/`)

```
data/
├── raw/                     # untouched upstream dumps, partitioned by job
├── processed/               # cleaned parquets the routers + ML read
├── geo/                     # static GeoJSON (TO bbox, Kamloops neighbourhoods)
├── firesmart/               # 30-action HIZ checklist JSON
├── models/                  # LightGBM weights + ONNX exports + metrics
├── wildfireiq.db            # SQLite
└── analytics.duckdb         # DuckDB
```

---

## End-to-end request lifecycle — "show me current fires on the globe"

```
1. Browser  GET /                                  → static HTML + main JS chunk (68 KB gz)
            ↓
2. main.tsx mounts <App/>; GlobeView mounts eagerly
   ↓
3. WildfireGlobe constructs the Cesium viewer + Ion terrain
   ↓
4. ActiveFiresLayer subscribes to useFiresCurrent() (TanStack Query hook)
   ↓
5. apiGet('/api/fires/current') → fetch http://localhost:8000/api/fires/current
   ↓
6. CORSMiddleware + CacheControlMiddleware tag the response
   ↓
7. routers/fires.py · async def current() ──┐
                                            │
8. _data.fires_current(include_extinguished=False)
   ↓
9. Read data/processed/fires_current.parquet (Pandas, lru-cached at the path level
   by the OS page cache)
   ↓
10. Filter rows where status != "Out" by default
   ↓
11. Pydantic Envelope[list] → ORJSONResponse → bytes
   ↓
12. Cache-Control: public, max-age=60   (set by the middleware)
   ↓
13. TanStack Query holds the result for refetchInterval=60s; the React component
    re-renders with the new fire entities
   ↓
14. ActiveFiresLayer translates each row to a Cesium Entity (Polygon or Billboard)
   ↓
15. viewer.scene.requestRender() fires; the WebGL canvas updates
```

The same shape applies to every other endpoint — `useFirmsHotspots`, `useEvacActive`, `useAqCurrent`, `useFwiToday`, `useSmokeForecast`, `useRiskGrid`, `useFireSmartChecklist`, `useClimateTrends`, etc. The router is always thin; the work is in the ingest job that produced the parquet hours earlier.

---

## Background pipeline — "how does data get into a parquet in the first place?"

APScheduler fires each `IngestJob` on its cron cadence. The base runner (`ingest/base.py · run_job`) wraps every job in:

1. **HTTPX client** with sensible timeouts.
2. **Tenacity retry** on transient HTTP errors.
3. **Structured logging** via structlog.
4. **`ingest_runs` row** written to SQLite when the job finishes — status, rows-in, rows-written, duration, error.

A typical job looks like:

```python
class FIRMSHotspotsJob(IngestJob):
    name = "firms_hotspots"
    cadence = "*/30 * * * *"   # every 30 min

    async def run(self, ctx) -> IngestReport:
        rows = []
        for source in ("VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT", "MODIS_NRT"):
            csv = await ctx.http.get(f".../FIRMS/area/csv/{KEY}/{source}/{bbox}/2")
            rows.extend(_parse_csv(csv.text))
        df = pd.DataFrame(rows)
        df.to_parquet(PROCESSED / "firms_hotspots_recent.parquet")
        return IngestReport(...)
```

On uvicorn startup, `refresh_stale_jobs(max_age_minutes=30)` runs any job whose last successful row in `ingest_runs` is older than 30 minutes — so a cold start gives fresh data on the first request instead of waiting for the next cron tick.

---

## ML inference path — "where does an AQ forecast number come from?"

```
Browser → /api/aq/forecast?hours=48
   ↓
routers/aq.py · forecast()
   ↓
ml/aq_infer.py:
   1. Read last 36 h of aq_hourly_kamloops.parquet (rolling state)
   2. For each horizon ∈ {1, 3, 6, 12, 24, 36, 48}:
        For each quantile ∈ {0.1, 0.5, 0.9}:
            booster = lgb.Booster(model_file=data/models/aq_forecaster_v1/h{H}/q{Q}.txt)
            X = build_features(last_36h)   # 20 cols
            y_hat = booster.predict(X)
   3. Assemble {horizon, q10, q50, q90} into a forecast trace
   ↓
Pydantic Envelope[list]  → ORJSONResponse
```

The wildfire risk path is the same shape but reads `data/models/wildfire_risk_v1/{model.txt, calibrator.joblib}` and produces a single regional probability per day, then multiplies it by each H3 cell's historical density.

---

## Build + deploy story

The whole platform is **local-first** by design:

- `pnpm dev` runs Vite on `:5173`.
- `pnpm dev:api` (or `uv run uvicorn wildfireiq_api.main:app --reload`) runs FastAPI on `:8000`.
- `pnpm build` produces a static `apps/web/dist/` that can be served from any static host.
- The backend is fine on a single uvicorn process; for production we'd put it behind Caddy with HTTP/2 + gzip + brotli, and pin the parquet dir to a persistent volume.

There's no Redis, no Celery, no Postgres. The Phase-1 architecture decision was explicit: single-process simplicity. Everything in `data/` is reproducible from the upstream feeds, so nothing in the repo is irreplaceable.

---

## What we deliberately did *not* build

- A user accounts system. Phase 5's preparedness hub is local-first (`localStorage` + IndexedDB) on purpose — no PII ever touches the backend.
- A separate microservice for ML inference. LightGBM is small; running inference inside the FastAPI process is fine and avoids cross-service serialisation.
- A custom tile server. Cesium Ion's free tier covers terrain + imagery; recreating that would burn the grant budget for no user-facing win.
- A Postgres / PostGIS layer. DuckDB queries the parquets directly and is fast enough at our scale.
