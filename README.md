# WildfireIQ Kamloops

**AI-powered wildfire risk, air quality, and community preparedness for the Thompson-Okanagan region of British Columbia.**

A research artifact built with a TRU Sustainability Research Grant (2025–2026) by Deeparsh Singh Dang. Open source under MIT (code) and CC-BY-4.0 (written content).

> **Informational only.** Not a substitute for the BC Wildfire Service, BC Emergency Management Climate Readiness, or Environment and Climate Change Canada.

---

## Features

| Surface | What it does |
|---|---|
| **`/` — 3D globe** | Province-wide BC Wildfire Service fires, NASA FIRMS satellite hotspots, BC EMCR evacuation zones, FWI stations, ECCC smoke forecast (73-step hourly scrubber), and an AI risk grid (185 H3 cells over the Thompson-Okanagan). Six toggleable layers, glassmorphic detail panels with date-sorted lists, location search, camera presets. |
| **`/air-quality`** | Live AQHI dial, 48-hour PM2.5 forecast with a q10–q90 uncertainty band, six-pollutant breakdown, a province-wide stations map, a rolling 365-day smoke calendar, Health Canada guidance, and opt-in AQHI-threshold web notifications. |
| **`/preparedness`** | A three-step onboarding wizard, a personalised FireSmart Home-Ignition-Zone checklist (30 actions, filtered by dwelling and situation, re-ordered by season), per-action photo capture (IndexedDB), a live point-in-polygon evacuation widget, a 12-badge achievement ladder with confetti, streak tracking, and a share-via-URL-hash link. All state is local — no accounts, no PII. |
| **`/climate`** | A six-section scrollytelling page: 27 years of area burned with landmark annotations, Theil-Sen trends with bootstrap confidence intervals, a fire-season ribbon, CMIP6 SSP projections, a decade-by-decade FWI≥19 estimate, and a feature-flagged TRU campus-carbon section. Every chart carries its source, method, and a CSV download; a print stylesheet emits a clean PDF. |

---

## Two real ML models

- **`wildfire_risk_v1`** — LightGBM binary classifier trained on 8,394 days × 40 features (1999–2021), validated on 2022, **tested on a held-out 2023 with PR-AUC 0.66 vs. an FWI-threshold baseline of 0.52**. The regional probability is multiplied by each H3 r=5 cell's historical fire density. Calibrated with isotonic regression. Card: [`documents/model-cards/wildfire_risk_v1.md`](./documents/model-cards/wildfire_risk_v1.md).
- **`aq_forecaster_v1`** — 21 LightGBM quantile models (7 horizons × q10/q50/q90) trained on co-located Open-Meteo CAMS hourly air quality + weather. **Beats the persistence baseline at the 6 h, 12 h, 36 h, and 48 h horizons.** Card: [`documents/model-cards/aq_forecaster_v1.md`](./documents/model-cards/aq_forecaster_v1.md).

The risk model is exported to ONNX with verified float32 parity (max |Δ| 7.89 × 10⁻⁸).

**Wildfire risk, in detail.** Each training row is one day described by ~40 features: current weather (temperature, humidity, wind, rain, vapour-pressure deficit), the six Van Wagner FWI codes, 7- and 30-day lags and rolling means, drought signals, and calendar terms. The label is whether a fire ignited in the region that day. The model is held strictly away from 2022 and 2023 during training; testing on those unseen years is what makes the PR-AUC trustworthy. At serving time the single regional probability is multiplied by each hexagon's square-root-normalised historical fire count to produce the per-cell grid, and the official CFFDRS Fire Danger class is shown alongside for comparison.

**Air quality forecaster, in detail.** Direct multi-horizon quantile regression: one LightGBM model per (horizon, quantile) pair. The median (q50) is the headline forecast; the q10 and q90 form the shaded uncertainty band so the chart widens when the model is unsure instead of pretending to be precise.

| AQ horizon | Model MAE (µg/m³) | Persistence baseline |
|---:|---:|---:|
| 6 h | 2.27 | 2.85 |
| 12 h | 3.20 | 4.06 |
| 24 h | 3.82 | 3.63 |
| 48 h | 3.32 | 3.92 |

---

## Data sources (every dependency is free)

| Need | Source | Auth | Coverage |
|---|---|---|---|
| Active fires | DataBC WFS (`openmaps.gov.bc.ca`) | None | All BC |
| Historical fires (15,996 incidents, 1999–) | DataBC `PROT_HISTORICAL_INCIDENTS_SP` | None | Thompson-Okanagan |
| Satellite hotspots | NASA FIRMS NRT (VIIRS / MODIS) | Free `MAP_KEY` | All BC |
| Weather + 10-day forecast | Open-Meteo GEM-HRDPS | None | Kamloops point |
| Weather archive (~10,000 daily rows) | Open-Meteo ERA5 + recent tail | None | Kamloops point |
| Fire Weather Index | Van Wagner port over Open-Meteo (NRCan CWFIS when reachable) | None | 18 BC stations |
| AQHI realtime | ECCC GeoMet | None | All BC |
| Pollutant breakdown | WAQI / AQICN | Free token | Kamloops |
| Air quality hourly + 365-day archive | Open-Meteo CAMS | None | Kamloops point |
| Smoke forecast | ECCC RAQDPS-FW via MSC GeoMet WMS | None | All BC overlay |
| Evacuation orders / alerts | BC Emergency Management ArcGIS | None | All BC |
| CMIP6 climate projections | ClimateData.ca structure (synthetic placeholder in this build) | None | Regional |
| Globe terrain + imagery | Cesium Ion (World Terrain + OSM Buildings) | Free Ion token | Global |

Three signups are required before running ingest: Cesium Ion, NASA FIRMS, WAQI. See [`documents/api-keys-setup.md`](./documents/api-keys-setup.md).

A per-layer breakdown of source, update cadence, computation method, and accuracy lives in [`documents/data-layer.md`](./documents/data-layer.md).

---

## Data pipeline

Seventeen ingest jobs run on cron cadences inside the FastAPI process (no Celery or Redis). Each job pulls from one upstream source, cleans the response, and writes a zstd-compressed Parquet file that the API serves. A run log is written to SQLite (`ingest_runs`) so failures are visible and retried on the next tick.

| Job | Cadence | Output |
|---|---|---|
| Active fires (DataBC) | every 15 min | `fires_current.parquet` |
| Satellite hotspots (FIRMS) | every 30 min | `firms_hotspots_recent.parquet` |
| Weather forecast (Open-Meteo) | hourly | `weather_kamloops_{current,hourly,daily}.parquet` |
| Weather archive + recent tail | daily 02:20 | `weather_kamloops_archive_daily.parquet` |
| Derived FWI (Van Wagner) | every 30 min | `fwi_stations_today.parquet` |
| AQHI realtime (ECCC GeoMet) | hourly | `aqhi_kamloops_recent.parquet` |
| Pollutants (WAQI) | hourly | `aq_pollutants_recent.parquet` |
| Air quality hourly (CAMS) | hourly | `aq_hourly_kamloops.parquet` |
| Air quality 365-day archive | daily 02:40 | `aq_hourly_kamloops.parquet` |
| Smoke forecast (RAQDPS-FW) | every 6 h | `smoke_forecast_metadata.parquet` |
| Evacuation (BC EMCR) | every 5 min | `evac_active.parquet` |
| Unified fires (derived) | daily 02:15 | `fires_unified.parquet` |
| Seasonal metrics (derived) | daily 02:30 | `seasonal_metrics.parquet` |

Bootstrap-only jobs (historical fires, ERA5 archive, CMIP6 placeholder, ECCC climate) run once via `make bootstrap`.

**Always-fresh launch.** On startup the backend checks every source and re-runs anything whose last successful run is older than 30 minutes, so the app (including the AI risk grid) shows current data within seconds of opening rather than waiting for the next cron tick.

---

## API surface

The backend exposes a small REST API; every response uses a `{data, meta}` envelope, and `meta` carries the source, attribution, and freshness. Full schema at `/docs` (OpenAPI).

| Group | Endpoints |
|---|---|
| Fires | `/api/fires/current`, `/api/fires/historical`, `/api/fires/hotspots` |
| Risk | `/api/risk/grid`, `/api/risk/today` |
| Air quality | `/api/aq/current`, `/api/aq/forecast`, `/api/aq/calendar`, `/api/aq/history`, `/api/aq/smoke-forecast`, `/api/aq/health-guidance` |
| Weather / FWI | `/api/weather/current`, `/api/weather/forecast`, `/api/fwi/today` |
| Evacuation | `/api/evac/active`, `/api/evac/check` |
| Preparedness | `/api/firesmart/checklist`, `/api/firesmart/score`, `/api/firesmart/achievements`, `/api/firesmart/neighbourhoods`, `/api/firesmart/season-context` |
| Climate | `/api/climate/seasonal`, `/api/climate/trends`, `/api/climate/ribbon`, `/api/climate/projection(s-all)`, `/api/climate/fwi-projection`, `/api/climate/tru-carbon` |
| Admin / system | `/api/admin/jobs`, `/api/admin/runs`, `/healthz` |

The climate endpoints accept `?format=csv` for the "Download CSV" buttons. Historical and reference endpoints carry a longer `Cache-Control` than live ones.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Browser (Desktop / iPad)                            │
│  ┌────────────────────────────────────────────────┐  │
│  │ React 18 + TS + Vite + Resium + Tailwind v4    │  │
│  │  • Cesium globe (eager)                        │  │
│  │  • AQ / Prep / Climate (React.lazy chunks)     │  │
│  │  • localStorage + IndexedDB for the prep hub   │  │
│  └────────────────────────────────────────────────┘  │
│           ▲ TanStack Query (REST / JSON)             │
└───────────┼──────────────────────────────────────────┘
            │ http://localhost:8000
┌───────────┴──────────────────────────────────────────┐
│  FastAPI (Python 3.12, uv workspace)                 │
│  ┌────────────────────────────────────────────────┐  │
│  │ /api/fires /api/risk /api/aq /api/firesmart    │  │
│  │ /api/evac  /api/fwi  /api/climate /api/weather │  │
│  └────────────────────────────────────────────────┘  │
│  Cache-Control middleware · DuckDB warm-up           │
│  APScheduler (17 ingest jobs)                        │
│  LightGBM inference · Van Wagner FWI port            │
└───────────────────┬──────────────────────────────────┘
                    │
┌───────────────────┴──────────────────────────────────┐
│  Storage (local, zero-cost)                          │
│  • SQLite — app metadata + ingest_runs               │
│  • DuckDB — analytics                                │
│  • Parquet (zstd) — every cached upstream batch      │
│  • data/models/ — LightGBM + ONNX artifacts          │
└──────────────────────────────────────────────────────┘
```

On launch the backend refreshes any source older than 30 minutes, so the app shows current data — including the AI risk grid — within seconds of opening. Full request lifecycle: [`documents/architecture.md`](./documents/architecture.md).

---

## Repository layout

```
WildFire-IQ/
├── apps/
│   ├── web/                  # React + Vite frontend
│   │   └── src/
│   │       ├── features/     # globe, air-quality, preparedness, climate
│   │       ├── lib/          # API client + hooks, Cesium helpers
│   │       ├── shell/        # AppShell, splash, rails
│   │       └── stores/       # Zustand UI state
│   └── api/                  # FastAPI backend
│       ├── wildfireiq_api/
│       │   ├── ingest/       # 17 IngestJob subclasses + registry
│       │   ├── ml/           # FWI port, trainers, inference, ONNX export
│       │   └── routers/      # one router per domain
│       └── tests/            # pytest suite
├── packages/
│   ├── design-tokens/        # CSS variables + Tailwind preset
│   └── shared-types/         # TS types generated from the OpenAPI schema
├── data/
│   ├── raw/                  # untouched upstream dumps
│   ├── processed/            # cleaned parquets the app reads
│   ├── geo/                  # static GeoJSON (region bbox, neighbourhoods)
│   ├── firesmart/            # FireSmart checklist JSON
│   └── models/               # trained LightGBM + ONNX artifacts
├── documents/                # all project documentation (see below)
├── scripts/ingest/           # bootstrap entrypoint
├── Makefile                  # bootstrap / train / test / build targets
└── README.md
```

---

## Documentation

All documentation lives in [`documents/`](./documents):

| File | Contents |
|---|---|
| [`logic.md`](./documents/logic.md) | Canonical end-to-end engineering log — what each phase ships and why |
| [`data-layer.md`](./documents/data-layer.md) | Per-layer source, cadence, computation, and accuracy reference |
| [`architecture.md`](./documents/architecture.md) | System diagram + request lifecycle |
| [`data-dictionary.md`](./documents/data-dictionary.md) | Every column of every processed parquet |
| [`implementation-plan.md`](./documents/implementation-plan.md) | The original phased build plan |
| [`api-keys-setup.md`](./documents/api-keys-setup.md) | How to obtain the three free API tokens |
| [`model-cards/`](./documents/model-cards) | Model cards for both ML models |

---

## Quick start

```bash
# 1. Install
pnpm install
cd apps/api && uv sync && cd ../..

# 2. Configure keys (.env at the repo root)
cp .env.example .env
# Add CESIUM_ION_TOKEN, FIRMS_MAP_KEY, WAQI_TOKEN

# 3. One-shot bootstrap of historical + static datasets
make bootstrap

# 4. Run both dev servers
pnpm dev
# Frontend → http://localhost:5173
# Backend  → http://localhost:8000  (OpenAPI at /docs)
```

### Make targets

```bash
make bootstrap         # one-shot historical + static ingest
make ingest-all        # run every recurring job once
make train-risk        # train the wildfire risk classifier
make train-aq          # train the AQ quantile forecaster
make seasonal-metrics  # rebuild seasonal_metrics.parquet
make fires-unified     # rebuild fires_unified.parquet
make research-assets   # mirror model cards into apps/web/public/research/
make test              # backend pytest suite
make typecheck         # frontend TypeScript check
make build             # production build of the frontend
```

---

## Project status

| Phase | Title | Status |
|---|---|---|
| 0 | Foundation, design system, monorepo scaffold | Complete |
| 1 | Data ingestion + ETL pipeline (17 jobs) | Complete |
| 2 | 3D Cesium globe + Wildfire Risk Map | Complete |
| 3 | ML models — wildfire risk + AQ forecaster | Complete |
| 4 | Air Quality Monitor (`/air-quality`) | Complete |
| 5 | Community Preparedness Hub (`/preparedness`) | Complete |
| 6 | Climate Trend Module (`/climate`) | Complete |
| 7 | Polish, performance, docs, tests | Complete (demo recording + on-device iPad testing remain) |

---

## Tests

```bash
make test                  # backend — 47 pytest (ingest, routers, data quality, trends)
cd apps/web && pnpm test   # frontend — 22 vitest (hooks + utilities)
```

---

## Known limitations (honest framing)

- **The AI risk grid uses one regional weather signal.** Differences between hexagons come from each area's fire history, not separate local weather. The grid is a planning aid, not an official warning; the canonical CFFDRS class is shown next to it.
- **The CMIP6 climate projections are a synthetic placeholder** with the correct shape, not the live ClimateData.ca download. The trend direction is illustrative; absolute values shift once the real ensemble is dropped into `data/processed/climate_projections.parquet` (no code change needed). This is disclosed on the climate page.
- **The decade-by-decade FWI projection is a coarse one-variable extrapolation**, disclosed in its method note.
- **Air quality forecasting is single-point (Kamloops).** It cannot see a smoke plume arriving from outside the region until local readings begin to rise.
- **Historical fires and the risk grid are scoped to the Thompson-Okanagan** by design; live hazard layers (fires, hotspots, evacuation, FWI, AQHI, smoke) cover the whole province.

---

## Citation & license

If you reference this work, see [`CITATION.cff`](./CITATION.cff).

- **Code** — MIT (see [`LICENSE`](./LICENSE)).
- **Written content** — CC-BY-4.0.
- **Third-party dependencies** — [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md).

Built with a Sustainability Research Grant from Thompson Rivers University. Uses open data from the BC Wildfire Service, NASA FIRMS, Environment and Climate Change Canada, BC Emergency Management Climate Readiness, Open-Meteo, ClimateData.ca, and Cesium Ion. Every chart in the platform attributes its source.
