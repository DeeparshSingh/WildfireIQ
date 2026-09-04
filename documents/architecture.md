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
FastAPI on Python 3.12 inside a uv workspace. APScheduler runs 16 recurring ingest jobs on cron cadences, alongside 3 one-shot bootstraps (19 in total). SQLAlchemy + aiosqlite for ops state (`ingest_runs` log). Parquet (zstd-compressed) for every cached upstream batch, read straight off disk with pandas per request.

Layout:

```
apps/api/wildfireiq_api/
├── main.py                  # FastAPI app, lifespan, middleware
├── settings.py              # pydantic-settings
├── db.py                    # SQLAlchemy engine + session_scope
├── scheduler.py             # APScheduler + dependency-ordered startup catch-up
├── ingest/                  # 16 IngestJob subclasses + registry.py
├── routers/                 # 1 router per domain
├── ml/                      # FWI port, trainers, inference
└── tests/                   # pytest — 78 tests
```

### Data (`data/`)

```
data/
├── raw/                     # untouched upstream dumps, partitioned by job
│                            #   (newest 24 snapshots per job; older ones pruned)
├── processed/               # cleaned parquets the routers + ML read
├── geo/                     # static GeoJSON (TO bbox, Kamloops neighbourhoods)
├── firesmart/               # 30-action HIZ checklist JSON
├── models/                  # LightGBM weights + metrics
├── wildfireiq.db            # SQLite
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
11. Pydantic Envelope[list] → JSONResponse → bytes
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

On uvicorn startup, `refresh_stale_jobs(max_age_minutes=30)` runs any job whose last successful row in `ingest_runs` is older than 30 minutes, so a cold start gives fresh data on the first request instead of waiting for the next cron tick.

Order matters there. `derived_risk_features` reads every region's weather archive and `derived_seasonal_metrics` reads the Kamloops archive; the nightly cron times are staggered to respect that (02:20 archive → 02:25 region weather → 02:30 seasonal → 02:35 risk features), but a catch-up run has no clock to lean on. So each job declares `depends_on`, `registry.dependency_waves()` groups a selection into waves, and the catch-up finishes one wave before starting the next while still running the jobs inside a wave in parallel. An unknown dependency name or a cycle raises at startup rather than silently reordering data.

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
Pydantic Envelope[list]  → JSONResponse
```

The wildfire risk path is the same shape but reads `data/models/wildfire_risk_v1/{model.txt, calibrator.joblib}`. It loops the four regions in `constants.REGIONS`, scores each from its own weather archive to get one probability per region per day, then multiplies that by each of the region's H3 cells' historical density. Every cell is claimed by exactly one region, so the 523 hexagons never overlap.

---

## How the frontend types API responses

`apps/web/src/lib/api/hooks.ts` declares the response types by hand, next to
the TanStack Query hook that fetches each one, and every router's Pydantic
model is the server-side counterpart.

An `openapi-typescript` generator and a `packages/shared-types` package existed
for this and were removed during the September 2026 audit: nothing imported the
generated file, so it had drifted (it predated the multi-region risk grid) while
claiming in its own description to be the single source of API contract truth. A
stale generated file that nobody reads is worse than none. If the hand-written
types become a maintenance problem, wire the generator into the build so it
cannot drift, rather than reintroducing it as an artifact someone has to
remember to regenerate.

---

## Raw snapshot retention

Every job keeps its untouched upstream response under `data/raw/<job>/`, which
makes a parse failure reproducible: you can see exactly what the source
returned. Left alone that grows without bound — `bcem_evac` writes a GeoJSON
every 5 minutes, and four months of running filled 1.3 GB.

So `IngestJob.raw_retention` caps it, defaulting to the newest 24 snapshots,
and `run_job` prunes after every run. A snapshot is one entry directly under
the job's folder: a file for jobs that write one blob per run, a directory for
jobs that write several (`databc_fires_current`, `firms_hotspots`). A bootstrap
whose raw files *are* the corpus sets `raw_retention = None`
(`eccc_climate_kamloops` keeps one CSV per year). `make prune-raw` trims an
existing checkout in one pass.

---

## Build + deploy story

The whole platform is **local-first** by design:

- `pnpm dev` runs Vite on `:5173`.
- `pnpm dev:api` (or `uv run uvicorn wildfireiq_api.main:app --reload`) runs FastAPI on `:8000`.
- `pnpm build` produces a static `apps/web/dist/` that can be served from any static host.
- The backend is fine on a single uvicorn process; for production we'd put it behind Caddy with HTTP/2 + gzip + brotli, and pin the parquet dir to a persistent volume.

There's no Redis, no Celery, no Postgres. That was an explicit early decision: single-process simplicity. Everything in `data/` is reproducible from the upstream feeds, so nothing in the repo is irreplaceable.

---

## What we deliberately did *not* build

- A user accounts system. The preparedness hub is local-first (`localStorage` + IndexedDB) on purpose — no PII ever touches the backend.
- A separate microservice for ML inference. LightGBM is small; running inference inside the FastAPI process is fine and avoids cross-service serialisation.
- A custom tile server. Cesium Ion's free tier covers terrain + imagery; recreating that would burn the grant budget for no user-facing win.
- A Postgres / PostGIS layer. At this scale pandas reads the parquets directly in single-digit to low-hundreds of milliseconds, and every dataset is reproducible from its upstream feed, so a database server would add operational weight without buying anything.
