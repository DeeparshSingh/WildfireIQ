# WildfireIQ Kamloops

**AI-powered wildfire risk, air quality, and community preparedness for the Thompson-Okanagan region of British Columbia.**

A research artifact built with a TRU Sustainability Research Grant (2025–2026) by Deeparsh Singh Dang.
Open source under MIT (code) and CC-BY-4.0 (written content).

> **Informational only.** Not a substitute for BC Wildfire Service, BC Emergency Management Climate Readiness, or Environment and Climate Change Canada guidance.

---

## What's in the box

| Surface | What it does |
|---|---|
| **`/` — 3D globe** | Live BC Wildfire Service fires, NASA FIRMS satellite hotspots, BC EMCR evacuation orders, NRCan FWI stations, ECCC RAQDPS-FW smoke forecast (73-step hourly scrubber), AI risk grid (185 H3 cells). 6 layers, glassmorphic detail modal, location search, camera presets. |
| **`/air-quality`** | AQHI dial, 48-hour PM2.5 forecast with q10–q90 uncertainty band, six-pollutant breakdown, nearby stations minimap, 365-day smoke calendar, Health Canada guidance with three audience tabs, opt-in AQHI-threshold web notifications. |
| **`/preparedness`** | Three-step onboarding wizard → personalised FireSmart HIZ checklist (30 actions, dwelling- and situation-filtered, season-ordered) with photo capture (IndexedDB), live evac point-in-polygon widget, 12-badge achievement ladder with confetti, streak tracking, share-via-URL-hash (no server hop). |
| **`/climate`** | Six-section scrollytelling page: 27 years of area burned with landmark annotations, Theil-Sen trends + bootstrap CIs on July temp / precip / VPD, fire-season ribbon, CMIP6 SSP1-2.6 / 2-4.5 / 5-8.5 projections with toggle, decade-by-decade FWI≥19 heuristic, feature-flagged TRU campus carbon. Each chart carries source, method, and CSV download. Print stylesheet emits a clean four-page PDF. |

---

## Two real ML models

- **`wildfire_risk_v1`** — LightGBM binary classifier trained on 8,394 days × 40 features (1999-2021), validated 2022, **tested 2023 with PR-AUC 0.66 vs. an FWI-threshold baseline of 0.52** (+ 15 points). Regional probability multiplied by H3 r=5 cell-density. Calibrated via isotonic regression. Card: [`docs/model-cards/wildfire_risk_v1.md`](./docs/model-cards/wildfire_risk_v1.md).
- **`aq_forecaster_v1`** — 21 LightGBM quantile models (7 horizons × q10/q50/q90) trained on co-located Open-Meteo CAMS hourly air-quality + weather. **Beats persistence at the 6 h, 12 h, 36 h, and 48 h horizons.** Card: [`docs/model-cards/aq_forecaster_v1.md`](./docs/model-cards/aq_forecaster_v1.md).

ONNX export of the risk model verified with float32 parity (max |Δ| 7.89 × 10⁻⁸). AQ ONNX bundle deferred — 21 separate quantile models.

---

## Data sources (every dependency is free)

| # | Need | Source | Auth |
|---|---|---|---|
| 1 | Active BC fires | DataBC WFS (`openmaps.gov.bc.ca`) | None |
| 2 | Historical fires (15,996 incidents 1999-2025) | DataBC `PROT_HISTORICAL_INCIDENTS_SP` | None |
| 3 | Satellite hotspots | NASA FIRMS NRT USFS | Free `MAP_KEY` |
| 4 | Weather + 10-day forecast | Open-Meteo GEM-HRDPS | None |
| 5 | Weather archive (9,992 daily rows) | Open-Meteo ERA5 | None |
| 6 | FWI | NRCan CWFIS (when reachable) + Van Wagner port over Open-Meteo | None |
| 7 | Air quality realtime | ECCC GeoMet AQHI + WAQI | Free token |
| 8 | Air quality hourly archive | Open-Meteo CAMS | None |
| 9 | Smoke forecast | ECCC RAQDPS-FW via MSC GeoMet WMS | None |
| 10 | Evacuation orders | BC Emergency Management ArcGIS FeatureServer | None |
| 11 | CMIP6 climate projections | ClimateData.ca (structurally-correct synthetic placeholder ships in this build) | None |
| 12 | Globe terrain + imagery | Cesium Ion (World Terrain + OSM Buildings) | Free Ion token |

Three signups required before running ingest: Cesium Ion, NASA FIRMS, WAQI. See [`docs/api-keys-setup.md`](./docs/api-keys-setup.md).

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Browser (Desktop / iPad)                            │
│  ┌────────────────────────────────────────────────┐  │
│  │ React 18 + TS + Vite + Resium + Tailwind v4    │  │
│  │  • Cesium globe (eager)                        │  │
│  │  • AQ / Prep / Climate (React.lazy chunks)     │  │
│  │  • localStorage + IndexedDB for prep hub       │  │
│  └────────────────────────────────────────────────┘  │
│           ▲ TanStack Query (REST/JSON)               │
└───────────┼──────────────────────────────────────────┘
            │ http://localhost:8000
┌───────────┴──────────────────────────────────────────┐
│  FastAPI (Python 3.12, uv workspace)                 │
│  ┌────────────────────────────────────────────────┐  │
│  │ /api/fires /api/risk /api/aq /api/firesmart    │  │
│  │ /api/evac  /api/fwi  /api/climate /api/weather │  │
│  └────────────────────────────────────────────────┘  │
│  Cache-Control middleware · DuckDB warm-up           │
│  APScheduler (16 ingest jobs, see registry)          │
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

Full diagram + request lifecycle: [`docs/architecture.md`](./docs/architecture.md).

---

## Quick start

```bash
# 1. Install
pnpm install
cd apps/api && uv sync && cd ../..

# 2. Configure keys (.env at repo root)
cp .env.example .env
# Edit .env to add CESIUM_ION_TOKEN, FIRMS_MAP_KEY, WAQI_TOKEN

# 3. One-shot bootstrap of historical + static datasets
make bootstrap

# 4. Run dev servers (concurrently)
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
make seasonal-metrics  # rebuild seasonal_metrics.parquet (Phase 6)
make fires-unified     # rebuild fires_unified.parquet
make research-assets   # mirror model cards into apps/web/public/research/
make test              # full pytest suite
make typecheck         # frontend TypeScript check
make build             # production build of the frontend
```

---

## Project status

| Phase | Title | Status |
|---|---|---|
| 0 | Foundation, design system, monorepo scaffold | ✅ |
| 1 | Data ingestion + ETL pipeline (16 jobs, 9,992 wx rows, 15,996 fires) | ✅ |
| 2 | 3D Cesium globe + Wildfire Risk Map | ✅ |
| 3 | ML models — wildfire risk classifier (PR-AUC 0.66) + AQ forecaster | ✅ |
| 4 | Air Quality Monitor (`/air-quality`) | ✅ |
| 5 | Community Preparedness Hub (`/preparedness`) | ✅ |
| 6 | Climate Trend Module (`/climate`) | ✅ |
| 7 | Polish, performance, iPad/desktop optimization, demo | in progress |

See [`logic.md`](./logic.md) for the canonical, end-to-end engineering log of what each phase ships and why.

---

## Tests

```bash
make test          # backend: 47 tests (ingest, routers, data quality, trends)
cd apps/web && pnpm test   # frontend: vitest hook + utility suite
```

---

## Citation

If you reference this work, see [`CITATION.cff`](./CITATION.cff).

## Acknowledgements

Built with a Sustainability Research Grant from Thompson Rivers University. Uses open data from BC Wildfire Service, NASA FIRMS, Environment and Climate Change Canada, BC Emergency Management Climate Readiness, Open-Meteo, ClimateData.ca, and Cesium Ion. Every chart in the platform attributes its source.

## License

- **Code** — MIT (see [`LICENSE`](./LICENSE)).
- **Written content** (model cards, this README, `logic.md`) — CC-BY-4.0.

Third-party dependency licenses: [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md).
