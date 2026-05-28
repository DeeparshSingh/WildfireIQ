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

## Citation & license

If you reference this work, see [`CITATION.cff`](./CITATION.cff).

- **Code** — MIT (see [`LICENSE`](./LICENSE)).
- **Written content** — CC-BY-4.0.
- **Third-party dependencies** — [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md).

Built with a Sustainability Research Grant from Thompson Rivers University. Uses open data from the BC Wildfire Service, NASA FIRMS, Environment and Climate Change Canada, BC Emergency Management Climate Readiness, Open-Meteo, ClimateData.ca, and Cesium Ion. Every chart in the platform attributes its source.
