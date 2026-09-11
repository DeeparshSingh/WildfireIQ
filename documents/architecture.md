# Architecture

The engineering reference for WildfireIQ: how the code is organised, how a
request is served, how data is ingested and scheduled, how the models are
run, and how the frontend is put together. It is written for someone who is
about to change the code. For the plain-language account of the data and
how to extend the platform, read [`how-it-works.md`](./how-it-works.md)
first; for every column of every file, [`data-dictionary.md`](./data-dictionary.md).

---

## 1. Shape of the system

Two applications in one repository, plus a data directory they share.

```
WildFire-IQ/
├── apps/
│   ├── api/                       FastAPI · Python 3.12 · uv
│   │   ├── wildfireiq_api/
│   │   │   ├── main.py            app factory, lifespan, middleware, router mounts
│   │   │   ├── settings.py        pydantic-settings; every env var is declared here
│   │   │   ├── constants.py       region geometry: BBOX_*, BC_BBOX_*, KAMLOOPS_*, REGIONS
│   │   │   ├── paths.py           data/ layout
│   │   │   ├── db.py              SQLite engine + the ingest_runs schema
│   │   │   ├── scheduler.py       APScheduler + dependency-ordered startup catch-up
│   │   │   ├── ingest/            17 IngestJob classes, base runner, registry, prune CLI
│   │   │   ├── ml/                FWI port, feature builder, two trainers, two inference modules, trends
│   │   │   ├── routers/           one router per domain + _data.py (parquet readers) + _envelope.py
│   │   │   └── assistant/         agent harness, 25 tools, OpenRouter transport, guard, evals
│   │   └── tests/                 220 pytest tests
│   └── web/                       React 18 · TypeScript · Vite · Cesium
│       └── src/
│           ├── main.tsx, app.tsx  providers, route table (lazy routes)
│           ├── shell/             AppShell, TopBar, LeftRail, Splash, ErrorBoundary
│           ├── stores/            Zustand: layers, filters, smoke, globe, assistant
│           ├── lib/api/           apiGet client + one TanStack Query hook per endpoint
│           ├── lib/cesium-helpers/ viewer init, cinematic flyTo, WKT parsing, render helpers
│           └── features/          globe · air-quality · preparedness · climate · about · assistant
├── packages/design-tokens/        CSS variables, fonts, reset (imported by the web app)
├── data/                          processed parquet, raw snapshots, models, geo, firesmart, SQLite
├── documents/                     this folder
├── scripts/ingest/bootstrap.py    one-time historical pull; also runs every job once
├── start.sh                       launches both halves; installs and bootstraps on first run
└── Makefile                       every documented command
```

The backend is a single uvicorn process. It runs the scheduler, the ingest
jobs, the models and the API in that one process. There is no queue, no cache
server and no database server; the data layer is Parquet files read with
pandas, and SQLite holds one operational table. This was chosen deliberately:
every dataset is reproducible from its public source, request volumes are
small, and one process is the easiest thing to hand over.

---

## 2. Serving a request

Every endpoint has the same shape. Taking active fires on the globe:

```
Browser  useFiresCurrent()                  TanStack Query hook, refetch every 60 s
   │      apiGet("/api/fires/current")
   ▼
API      CORSMiddleware → CacheControlMiddleware
         routers/fires.py::current()
         _data.fires_current()              pd.read_parquet(data/processed/fires_current.parquet)
         Envelope(data=rows, meta=Meta(source, attribution, note, cached_at))
   │      Cache-Control: public, max-age=60
   ▼
Browser  ActiveFiresLayer                    rows → Cesium entities (polygon or billboard)
```

Rules that hold everywhere:

- **Routers are thin.** They call a reader in `routers/_data.py` and wrap the
  result. Routers never fetch from an upstream service.
- **Readers are the only place parquet is opened.** `_data.py` handles a
  missing file (returns empty) and NaN → `null`, so every endpoint degrades
  the same way.
- **Every response is an envelope:** `{"data": …, "meta": {"source",
  "attribution", "note", "cached_at"}}`. `meta.note` carries caveats the UI
  shows (for example, why the climate series ends a year early).
- **Cache-Control is set by path.** `/api/*` defaults to `public, max-age=60`;
  historical and reference endpoints (`/api/climate/*`, `/api/firesmart/*`,
  `/api/aq/health-guidance`, `/api/aq/calendar`, `/api/fires/historical`) get
  `max-age=300, s-maxage=600`; `/api/assistant/*` is `no-store`.
- **CORS** allows the Vite dev origins on 5173 by default (`CORS_ORIGINS`).

### Endpoints

| Path | Method | Consumer |
|---|---|---|
| `/healthz` | GET | ops |
| `/api/fires/current`, `/hotspots` | GET | globe |
| `/api/fires/historical` | GET | no caller in this repo |
| `/api/risk/grid` | GET | globe |
| `/api/weather/current`, `/forecast` | GET | no caller in this repo (the assistant reads the same parquet in-process) |
| `/api/fwi/today` | GET | globe |
| `/api/aq/current`, `/forecast`, `/calendar`, `/smoke-forecast`, `/health-guidance` | GET | air quality page, globe |
| `/api/aq/history` | GET | no caller in this repo |
| `/api/evac/active`, `/check?lat=&lon=` | GET | globe, preparedness |
| `/api/firesmart/checklist`, `/achievements`, `/neighbourhoods`, `/season-context` | GET | preparedness |
| `/api/climate/seasonal`, `/trends`, `/ribbon`, `/projections-all`, `/fwi-projection`, `/tru-carbon` | GET | climate page; `seasonal` and `ribbon` accept `?format=csv` |
| `/api/climate/projection?ssp=&var=` | GET | no caller in this repo; the only projection route with `?format=csv` |
| `/api/admin/jobs`, `/runs` | GET | ops |
| `/api/admin/jobs/{name}/run` | POST | ops |
| `/api/assistant/chat` | POST | assistant panel (SSE; `?stream=false` for JSON) |
| `/api/assistant/health`, `/tools`, `/brief` | GET | assistant panel, ops |

Four endpoints are marked "no caller in this repo". That is literal: the web
app does not fetch them, the assistant reads the same data in-process rather
than over HTTP, and the platform is not hosted, so there are no external
clients either. They are kept because each is the only HTTP route to a dataset
the platform ingests — Kamloops weather, the 96,000-record fire archive,
per-station AQHI over time, and a CSV export of a single projection scenario —
and they are covered by `tests/test_routers.py` so they cannot rot silently.

Two others were removed in the September 2026 audit rather than kept on the
same reasoning, because neither was the only route to anything:

- `GET /api/risk/today?cell=` computed the full 523-cell grid and then returned
  one cell. `/api/risk/grid`, which the globe already fetches, contains that
  cell. It was a performance trap for any caller that found it.
- `POST /api/firesmart/score` was a second implementation of the badge ladder,
  mirroring rules that the preparedness page evaluates locally. Two copies of a
  rule set that must be hand-synchronised is the same failure mode that had
  already rotted the generated-types package.

The interactive OpenAPI page is at `/docs`.

---

## 3. Ingest

### The job contract

Every source is a subclass of `IngestJob` (`ingest/base.py`):

```python
class FIRMSHotspotsJob(IngestJob):
    name = "firms_hotspots"              # unique; also the folder under data/raw/
    label = "NASA FIRMS · satellite hotspots"
    cadence = "*/30 * * * *"             # cron, UTC; None for a one-time bootstrap
    raw_retention = 24                   # raw snapshots to keep (default)
    depends_on = ()                      # names of jobs whose output this one reads

    async def run(self, ctx: IngestContext) -> IngestReport:
        ...                              # fetch → normalise → write one parquet
```

`run_job()` wraps every execution with: an `httpx.AsyncClient` carrying the
project User-Agent; **tenacity** retries (3 attempts, exponential back-off 1–10 s)
on HTTP and connection errors; structured logging; pruning of `data/raw/<name>/`
to the newest `raw_retention` entries; and a row in SQLite `ingest_runs`
(status `ok | partial | fail`, rows in/out, duration, note, error). A job that
raises is recorded as `fail`; it never takes the process down.

Jobs are listed in `ingest/registry.py`. `all_jobs()` is the single source of
truth; `scheduled_jobs()` and `bootstrap_jobs()` partition it by whether
`cadence` is set. Seventeen jobs today: 15 recurring, 2 one-time. The full
schedule is in `how-it-works.md` §4.1.

### Scheduling

`scheduler.py` registers each recurring job with APScheduler (`AsyncIOScheduler`,
UTC, `max_instances=1`, `coalesce=True`, `misfire_grace_time=300`). The
scheduler starts inside the FastAPI lifespan and can be disabled with
`SCHEDULER_ENABLED=false` (tests do this).

### Startup catch-up

`refresh_stale_jobs(30)` runs in the background at boot:

1. Select every recurring job whose last `ok` row in `ingest_runs` is older
   than 30 minutes (`STARTUP_REFRESH_MINUTES`).
2. Widen the selection with `registry.with_dependents()` so anything that
   reads a selected job's output is rebuilt too — otherwise a derived file
   can end up older than its inputs.
3. Group with `registry.dependency_waves()`; run each wave with a
   concurrency of 5, next wave only when the previous completes.

An unknown `depends_on` name or a cycle raises at startup. The nightly cron
times are staggered to the same order (02:20 archive → 02:25 region weather →
02:30 seasonal → 02:35 risk features), and `tests/test_pipeline.py` asserts the
cron order and the declared graph agree.

### Running jobs by hand

```bash
./start.sh --bootstrap                                  # historical pulls + every job once
make ingest-all                                         # every recurring job once
uv run --project apps/api python -m wildfireiq_api.scheduler run <job_name>
curl -X POST localhost:8000/api/admin/jobs/<job_name>/run
make prune-raw                                          # trim data/raw to retention
```

### Geometry constants

`constants.py` holds every coordinate the backend uses: `BC_BBOX_*` bounds the
province-wide feeds (fires, hotspots, evacuations, FWI, AQHI, smoke);
`BBOX_*` is the Thompson-Okanagan box used by the climate page; `KAMLOOPS_*`
is the point used by the Kamloops weather, air-quality and WAQI jobs; and
`REGIONS` is the list the risk model, the feature builder, region weather,
inference, the gazetteer and the tests all read. There is no second copy of
any of these.

---

## 4. Models

Both models are LightGBM and are loaded once per process with `lru_cache`.

### Wildfire risk — `ml/risk_infer.py::predict_grid()`

```
for region in REGIONS:
    weather  = read weather_<region>_archive_daily.parquet
    features = ml.features._enrich_weather(weather)         # FWI codes, lags, means, drought, calendar
    row      = last day with a complete feature vector
    p_raw    = booster.predict(row[FEATURE_COLS])            # data/models/wildfire_risk_v1/model.txt
    p_cal    = calibrator.predict(p_raw)                     # isotonic, calibrator.joblib
    for cell in cell_density[region]:
        p_cell = p_cal × cell.weight                         # weight = sqrt-normalised fire count
        class  = Low <0.05 | Moderate <0.20 | High <0.50 | Extreme
    region.risk_level = highest class covering ≥15% of its cells
    region.cffdrs_class = cffdrs_class_for(fwi)              # Low ≤1 · Moderate 2–4 · High 5–12 · Very High 13–20 · Extreme ≥21
```

Training (`make train-risk`, `ml/train_risk.py`): pooled over all regions,
train 1999–2021, validate 2022, test 2023, early stopping, isotonic
calibration on 2022, per-region metrics to `metrics.json`. `region_fire_rate`
is computed from ≤2021 only (`features.BASE_RATE_MAX_YEAR`). Features are built
by the same code path the nightly `derived_risk_features` job runs, so training
and inference cannot disagree about a feature.

### Air quality — `ml/aq_infer.py::predict_forecast()`

Reads the latest rows of `aq_hourly_kamloops.parquet`, builds the feature
vector (`train_aq._enrich`), and for each horizon in {1, 3, 6, 12, 24, 36, 48}
predicts q10, q50, q90 with the corresponding booster. The band is then
**conformalised**: q10 and q90 are pushed out by that horizon's factor from
`conformal.json` times the band's own width, floored at zero and sorted. That
step is what makes the band a calibrated ~80% interval — raw, it covers 59-68%
— and a missing `conformal.json` degrades to no widening rather than an error.
The response carries a `band` object reporting nominal and measured coverage,
so the chart describes itself from the model that produced it.

`pm25_to_aqhi()` applies Health Canada's PM2.5 term. `predict_calendar(days)`
is the daily max/mean aggregation behind the smoke calendar.

Training: `make train-aq`. The models are fitted on the first 70% of the record
chronologically; the remaining 30% is split at random into a calibration third,
which sets the conformal factor, and a test two-thirds, which is what every
reported number is measured on. `tests/test_aq_calibration.py` pins the factor's
arithmetic and asserts the shipped band measures close to nominal.

### Fire Weather Index — `ml/fwi.py`

A vectorised pandas implementation of Van Wagner & Pickett (1985): FFMC, DMC,
DC, ISI, BUI, FWI, DSR from daily noon temperature, humidity, wind and 24-hour
rain, with standard start-up values and month-dependent day-length factors.
Used by the feature builder (per region), the seasonal metrics (Kamloops), and
the `derived_fwi_stations` job (18 towns).

### Trends — `ml/trends.py`

`theil_sen_with_ci(x, y, n_boot=1000)`: median of pairwise slopes, bootstrap
95% interval. Used by `/api/climate/trends`.

---

## 5. Frontend

### Routing and loading

`app.tsx` mounts the globe eagerly and code-splits every other route with
`React.lazy`; after the splash, the three heaviest routes are prefetched on
idle. `AppShell` renders the rail, the top bar, the Cesium viewer (once, for
the life of the app), the route content as a pointer-events-none overlay, and
the assistant dock.

### State

| Store | Holds |
|---|---|
| `stores/layers.ts` | which of the six layers are visible, the selected feature, which detail modal is open |
| `stores/filters.ts` | per-layer filters (include extinguished, min hectares, hotspot confidence and window, evac statuses, min FWI, hidden risk regions) |
| `stores/smoke.ts` | the smoke layer's current timestep index |
| `stores/globe.ts` | the Cesium `Viewer`, whether the intro has played, the data gate, the last camera |
| `stores/assistant.ts` | the conversation, mirrored to `sessionStorage` |

### Data hooks

`lib/api/hooks.ts` declares one TanStack Query hook per endpoint with a
hand-written response type and a refetch interval matched to the data (60 s
fires/evac/AQHI; 5 min hotspots; 10 min FWI and AQ forecast; 30 min smoke and
risk grid; 60 min calendar and season context; 24 h for reference data). The
types are maintained by hand next to the hooks; a generated-types package was
removed in the September 2026 audit because nothing consumed it and it had
drifted.

### The globe

`WildfireGlobe.tsx` creates the Cesium viewer through Resium, applies Ion
terrain and Bing aerial imagery, and plays a one-time intro flight from space
to Kamloops. The intro's `complete` callback opens the **data gate**
(`useGlobeStore.dataGateOpen`); every layer waits on that gate before
rendering entities, so nothing draws while the camera is still in space. The
intro effect runs exactly once per viewer, guarded by a ref, and reads its
start-up values imperatively rather than subscribing to them; subscribing to
`lastCamera`, which the camera listener rewrites on every movement, is what
had been resetting every flight before it could finish. `requestRenderMode`
is on outside of flights so the globe does not burn GPU while idle.

Layers live in `features/globe/layers/`. `LayerToggleBar` and
`LayerDetailModal` share `layerInfo.ts` for the per-layer explanations,
sources and refresh cadences shown to users.

### Preparedness: the privacy contract

Everything the hub stores stays in the browser:

| Where | Key | What |
|---|---|---|
| `localStorage` | `wildfireiq.profile.v1` | neighbourhood, dwelling, season, situation, notification preferences |
| `localStorage` | `wildfireiq.progress.v1` | completed actions, streak, flags |
| IndexedDB | `wildfireiq.progress.v1` / `photos` | photo blobs |
| URL hash | `/preparedness/shared#<base64>` | the share link encodes profile + progress client-side; photos are never included |

The only coordinate sent to the server is the neighbourhood centroid, to
`/api/evac/check`, and it is not logged with any identifier. The badge rules
run on the client. The catalogue of the twelve badges is served by
`/api/firesmart/achievements` so any future surface shows the same list, but the
rules that award them live in the client alone.

### Climate page

Six scroll-revealed sections over one derived table (`seasonal_metrics`):
area burned with landmark seasons; Theil-Sen trends for July temperature,
summer precipitation and VPD; a season-length ribbon; scenario projections
(placeholder, labelled); the FWI≥19 heuristic by decade; and the TRU-carbon
section, which renders only when `VITE_ENABLE_TRU_CARBON=true` and
`data/tru_carbon.csv` exists (columns `year`, `tco2e`, optional `target`).
Charts are Visx; every section carries source, method and a CSV link.

### Assistant panel

`features/assistant/` holds the panel, the trigger in the top bar, an SSE
reader over `fetch`, a markdown renderer that builds elements (never
`innerHTML`), and `useAssistant`, which applies streamed **effects** to the
globe store, the layers store and the router. Its design is in
[`assistant.md`](./assistant.md).

---

## 6. Configuration

### API keys

Credentials are not configuration and do not live in `.env`. They are entered
in the Settings panel (`shell/SettingsPanel.tsx`), and there are two kinds.

**Visitor keys** stay in the visitor's browser (`lib/keys.ts`, local storage)
and never reach the server store. The Cesium Ion token is used only by the
browser. A visitor's own OpenRouter key is sent as `X-OpenRouter-Key` with each
chat request and used for that request alone (`assistant/router.py`); the
assistant is therefore usable on a deployment whose owner has set no key.

**Server keys** are the owner's, one set per deployment, held by `keys.py` in
`data/runtime/keys.json` (ignored by git): the NASA FIRMS key and WAQI token
drive scheduled jobs, and an OpenRouter key is the default for visitors without
their own. `GET /api/settings/keys` reports whether each is set and whether
writes are protected; values are never returned. `PUT /api/settings/keys`
saves them and runs the ingest behind any newly added key at once. When
`ADMIN_TOKEN` is set, `PUT` requires the matching `X-Admin-Token` header.

| Key | Kind | Used by | Unlocks |
|---|---|---|---|
| Cesium Ion access token | visitor | browser | Terrain and imagery; without it the globe shows a notice that opens Settings |
| OpenRouter API key | visitor or server | assistant, per request or as default | The assistant; with neither, the Ask button opens Settings |
| NASA FIRMS map key | server | `firms_hotspots` job | Satellite hotspots layer |
| WAQI token | server | `waqi_kamloops` job | Pollutant breakdown |

`ADMIN_TOKEN` unset means writes are open, which is fine for one person on a
laptop and the panel says so. Set it before the API is reachable by anyone else.

### Owner control

`owner.py` decides whether a request may proceed, and `OwnerControlMiddleware`
in `main.py` enforces it ahead of every other middleware.

The owner holds an Ed25519 private key on their own machine
(`~/.wildfireiq/owner_ed25519`); the public half is in `owner.py`.
`scripts/owner.py` signs a small
JSON payload naming a state (`running`, `readonly`, `paused`), a message and a
timestamp. The deployment reads a standing command from a file
(`data/runtime/control.json`), an environment variable (`WILDFIREIQ_CONTROL`),
or a URL the owner controls (`OWNER_CONTROL_URL`, polled), and obeys the newest
valid one. `/api/ownership` reports the state and the key fingerprint, which
the owner compares against `scripts/owner.py whoami`.

Three properties are deliberate:

- **Fail-open.** A missing, unreadable, forged or unreachable command leaves
  the deployment running and logs the problem. A control plane that fails
  closed eventually locks out its owner.
- **No rollback.** The highest accepted `issued_at` is kept in
  `data/runtime/control_seen.json`; an older command is refused and the
  standing one is retained, so a captured `running` cannot undo a later
  `paused`.
- **Never self-locking.** `/healthz` and everything under `/api/ownership`
  answer even while paused, so the route that lifts a pause is never blocked
  by the pause.

`POST /api/ownership/state` is a weaker, everyday alternative authorised by the
admin token rather than a signature. Whichever instruction is most recent wins,
so neither channel can strand the other.

What this does not do: stop somebody with the source and root on the machine
from deleting the check. Nothing in software does. What it does is make that
change visible — a deployment that no longer reports the owner's fingerprint is
visibly not the owner's.

### Configuration

All backend settings are fields on `settings.Settings` and read from the
repository-root `.env`, which is optional: every setting has a working default. All frontend settings are `VITE_*` variables read at
build time.

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Where the web app finds the API |
| `VITE_ENABLE_TRU_CARBON` | `false` | Shows climate section 6 when the CSV exists |
| `ADMIN_TOKEN` | generated | Protects server keys and the pause control. Generated into `data/runtime/owner.json` on first boot when unset; `make admin-token` prints it |
| `OWNER_CONTROL_URL` | — | A URL holding a signed control command, polled while running |
| `OWNER_CONTROL_POLL_SECONDS` | `180` | How often that URL is re-read |
| `SERVE_WEB` | `true` | Serve `apps/web/dist` from the API, so browser and API share one origin |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/wildfireiq.db` | SQLite location |
| `CORS_ORIGINS` | the two Vite dev origins | |
| `SCHEDULER_ENABLED` | `true` | Run the cron jobs in-process |
| `STARTUP_REFRESH_MINUTES` | `30` | Staleness threshold for the boot catch-up |
| `BBOX_WEST/SOUTH/EAST/NORTH`, `KAMLOOPS_LAT/LON` | from `constants.py` | Overridable, normally left alone |
| `ASSISTANT_ENABLED`, `ASSISTANT_MODEL` | `true`, `z-ai/glm-5.3-flash` | |
| `ASSISTANT_MAX_STEPS`, `ASSISTANT_MAX_TOOL_CALLS`, `ASSISTANT_TIMEOUT_S` | `5`, `12`, `90` | Per-question budgets |
| `ASSISTANT_MAX_OUTPUT_TOKENS`, `ASSISTANT_REASONING_EFFORT` | `3000`, `low` | Output budget and thinking effort per turn |
| `ASSISTANT_RATE_PER_MINUTE`, `ASSISTANT_RATE_PER_HOUR`, `ASSISTANT_MAX_CONCURRENT`, `ASSISTANT_DAILY_COST_LIMIT_USD` | `4`, `30`, `4`, `2.0` | Abuse and spend limits |
| `ASSISTANT_REFERER`, `ASSISTANT_TITLE` | repository URL, app name | Attribution headers sent to OpenRouter |

---

## 7. Testing and quality

| Suite | Where | Count | Covers |
|---|---|---|---|
| Backend | `apps/api/tests/` | 220 (+3 `live`) | ingest parsers and schemas (`test_ingest`), data quality bounds, the air-quality band's conformal calibration (`test_aq_calibration`), every router, risk-region rules (no cell in two regions; badge matches cells), pipeline graph and cron agreement, raw retention, and the assistant (81: loop, budgets, fan-out, tool errors, SSE framing, guard, evals integrity), the two Fire Weather Index sources (`test_fwi_sources`: the renamed CWFIS layer, client-side bbox filtering, and the season-start spin-up the Drought Code needs), and the runtime key store and Settings API (`test_keys`: persistence, values never echoed, unknown names rejected, the admin token, the CORS preflight the panel depends on), a visitor's per-request assistant key, and owner control (`test_owner`: only the owner's key signs a command, a tampered or replayed one is refused, every failure leaves the deployment running, and a pause never blocks the route that lifts it) |
| Frontend | `apps/web/src/lib/__tests__/` | 67 | AQ colour scale, evacuation sorting, preparedness state and share encoding, the assistant's SSE reader and markdown renderer, the WKT parser behind the globe's fire and evacuation polygons (`wkt`), the data-unavailable banner (`dataNotice`, including the paused-query case that never reaches `isError`), and the API-key store, Settings panel and key notices (`keys`: storage round-trip, masked fields, visitor keys never leave the browser, server saves carry the admin token, notices follow the server's report) |
| Lint | | | `ruff check` + `ruff format --check`; Biome for TypeScript; `tsc --noEmit` |
| Live | | 32 cases | `make assistant-eval` runs the assistant against the real model; the only check that spends money (~$0.04 a sweep) |

```bash
make lint && make test && make typecheck && make build && (cd apps/web && pnpm test)
```

All of it runs in under a minute and needs no network except the live eval.

---

## 8. Operating it

- **Start:** `./start.sh` (installs on first run, bootstraps if the historical
  data is missing, then runs both halves). `pnpm dev` does the last step alone.
- **Build:** `make build` produces `apps/web/dist/`, a static bundle. The API
  is a plain uvicorn process; behind a reverse proxy, put the parquet
  directory on persistent storage and keep it to one worker (the scheduler
  and the assistant's limits are in-process).
- **When a feed breaks:** the last good file keeps serving; the failure is in
  `ingest_runs` (`/api/admin/runs?job=…`) and in the logs; the next tick
  retries. `cwfis_fwi_daily` had failed for the whole build against a
  diagnosis that was wrong — NRCan renamed the WFS layer, and the broad
  `except` reported it as an outage. Fixed; it now runs green as a
  cross-check on the FWI the platform computes itself.
- **Disk:** `data/raw` is capped at 24 snapshots per job (~150 MB);
  `data/processed` is ~60 MB; models ~27 MB.

### Deliberately not built

- User accounts or any server-side personal data.
- A separate inference service; LightGBM in-process is milliseconds.
- A database server or a task queue; pandas over Parquet and APScheduler in
  one process fit the scale and are simplest to hand over.
- A vector index for the assistant; its corpus is six markdown documents and
  term-overlap over headings finds the right section.
- Server-side conversation storage; the browser owns the transcript.
