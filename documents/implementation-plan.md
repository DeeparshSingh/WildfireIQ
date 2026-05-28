# WildfireIQ Kamloops — Implementation Plan

> **Project**: An AI-powered wildfire risk, air quality, and community preparedness platform for the Thompson-Okanagan region of British Columbia.
> **Build mode**: AI-first, agent-driven implementation in Claude Code (Sonnet 4.6 / Opus 4.7).
> **Deployment**: Local-only during build. Web app, no cloud cost. Open source on completion.
> **Author**: Deeparsh Singh Dang — TRU Sustainability Research Grant 2025-2026.
> **This document is the single source of truth.** Each phase is self-contained — invoke with `go phase N` once the previous phase is verified.

---

## 0. Vision & Non-Negotiables

### What we are building
A 3D-globe-centric web platform with four connected features:

1. **Wildfire Risk Map** — interactive 3D Cesium globe of the Thompson-Okanagan with daily AI-predicted fire risk zones (Low / Moderate / High / Extreme), live BC Wildfire Service incidents, and NASA FIRMS satellite hotspots overlaid.
2. **Air Quality Monitor** — Kamloops AQHI live + 48-hour AQ/smoke forecast (ML-driven) + historical smoke event calendar.
3. **Community Preparedness Hub** — neighbourhood-tailored FireSmart checklist, live evacuation orders for the user's area, and local-storage-backed points/achievement system (no accounts, no PII).
4. **Climate Trend Module** — 30-year (or longest available, ≥10) Thompson-Okanagan fire-season severity chart alongside projected temperature & precipitation shifts from ClimateData.ca / CMIP6.

### Aesthetic direction (locked)
**Tactical / intelligence-grade dark UI** — direct lineage to Bilawal Sidhu's "WorldView" reference but built natively for wildfire/AQ data. Think: dark base, bioluminescent fire-orange and ember-amber accents on critical data, glassmorphic side panels, subtle CRT scan-lines on the globe view, monospace data readouts paired with a high-character display font, atmospheric noise + grain overlays, animated camera fly-throughs as the user toggles features.

This is **not** a generic dashboard. It is a cinematic, mission-control feel that makes wildfire data feel as urgent and consequential as it is.

### Non-negotiables (these constrain every decision below)
- **Free or zero-cost** APIs/services only. Every external dependency is on a free tier with documented quotas.
- **No PII stored**. Local-only progress tracking via `localStorage`/IndexedDB.
- **Butter-smooth on iPad and desktop/laptop**. 60 fps target on Cesium globe, cold load < 3 s on a fibre connection.
- **Real ML models**, trained on historical data, validated against held-out 2022 + 2023 fire seasons. No fake heuristics dressed up as AI.
- **Open source**. All code released under MIT/Apache-2.0 at end of grant.
- **Frontend-design skill rules apply absolutely**: no Inter/Roboto/Arial, no purple-on-white gradients, no cookie-cutter layouts. Bold, intentional, distinctive.

---

## 1. Tech Stack (locked)

| Layer | Choice | Why |
|---|---|---|
| Frontend framework | **React 18 + TypeScript + Vite** | Fast HMR, modern, huge Cesium ecosystem support |
| 3D globe | **CesiumJS 1.120+ via Resium 1.19+** | Industry standard, free Ion tier, declarative React bindings |
| Styling | **Tailwind CSS v4 + CSS variables + custom design tokens** | Frontend-design skill explicitly endorses CSS variables; Tailwind v4 supports CSS-first config |
| State | **Zustand** for UI state, **TanStack Query v5** for server state | Lightweight, no Redux ceremony |
| Animation | **Motion (framer-motion v11)** for React, **GSAP** for camera fly-throughs | Skill explicitly recommends Motion |
| Charts | **Visx** (Airbnb) + **D3 v7** for custom viz; **Plotly.js** for the climate timeseries | Visx > Recharts for distinctiveness |
| Maps (2D fallback) | **MapLibre GL JS** (free, open) | Cesium 2D mode is heavy; MapLibre for the AQ Monitor's small inset map |
| Backend framework | **FastAPI 0.110+** on **Python 3.11+** | Async, type-hinted, OpenAPI free, ML-friendly |
| ML libraries | **scikit-learn 1.4+, XGBoost 2.0+, LightGBM, pandas, numpy, geopandas, rasterio, xarray** | Standard tabular + spatial stack |
| Data store | **SQLite + SQLAlchemy 2.0** for app state; **DuckDB** for analytical queries on the historical fire/weather/AQ corpus; **Parquet** for cached raw ingest | DuckDB is essential for fast 25-yr analytics; SQLite for transactional |
| Background jobs | **APScheduler** inside FastAPI for periodic ingest (no Celery/Redis needed locally) | Single-process simplicity |
| Package mgmt | **pnpm** (frontend), **uv** (Python) | Fast, modern |
| Lint/format | **Biome** (frontend), **ruff + ruff-format** (Python) | One tool each, zero config drama |
| Testing | **Vitest + React Testing Library** (frontend), **pytest + httpx** (backend) | Standard |

### Architecture

```
┌──────────────────────────────────────────────────────┐
│  Browser (iPad / Desktop)                            │
│  ┌────────────────────────────────────────────────┐  │
│  │ React + TS + Vite + Resium + Tailwind          │  │
│  │  • Cesium globe (Phase 2)                      │  │
│  │  • AQ monitor inset (Phase 4)                  │  │
│  │  • Prep hub (Phase 5, localStorage)            │  │
│  │  • Climate charts (Phase 6, Visx)              │  │
│  └────────────────────────────────────────────────┘  │
│                       ▲ TanStack Query (REST/JSON)   │
└───────────────────────┼──────────────────────────────┘
                        │  http://localhost:8000
┌───────────────────────┼──────────────────────────────┐
│  FastAPI backend (Python)                            │
│  ┌────────────────────────────────────────────────┐  │
│  │ /api/risk          — wildfire risk model       │  │
│  │ /api/aq            — AQ + 48-hr forecast       │  │
│  │ /api/fires         — current incidents+FIRMS   │  │
│  │ /api/evac          — evacuation orders         │  │
│  │ /api/climate       — historical & projections  │  │
│  │ /api/firesmart     — checklist content         │  │
│  └────────────────────────────────────────────────┘  │
│  APScheduler ingest jobs (15 min / hourly / daily)   │
│  ML inference: scikit-learn / XGBoost                │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────┴──────────────────────────────┐
│  Storage (local)                                     │
│  • SQLite — app metadata, cached API responses        │
│  • DuckDB — historical fires, weather, AQ analytics  │
│  • Parquet files — raw ingested batches              │
│  • models/ — trained sklearn/xgb pickles + ONNX      │
└──────────────────────────────────────────────────────┘
```

---

## 2. Data Sources (all free, all confirmed)

| # | Need | Source | Auth | Quota | Format |
|---|---|---|---|---|---|
| 1 | Active BC fire perimeters & points | DataBC WFS (`openmaps.gov.bc.ca`) | None | unlimited polite | GeoJSON |
| 2 | Satellite hotspots | NASA FIRMS Area API (USFS NRT endpoint) | Free MAP_KEY | 5,000 / 10 min | CSV/JSON |
| 3 | Historical BC fires (≥1999) | DataBC `PROT_HISTORICAL_FIRE_POLYS_SP` bulk | None | bulk | GeoJSON/SHP |
| 4 | Weather + 10-day forecast Kamloops | Open-Meteo (model `gem_hrdps_continental`) | None | 10k/day | JSON |
| 5 | Fire Weather Index | CWFIS GeoServer WFS + daily GeoTIFFs | None | unlimited polite | GeoJSON/GeoTIFF |
| 6 | Air quality realtime | ECCC GeoMet AQHI + WAQI backup | None / free token | unlimited | GeoJSON/JSON |
| 7 | Smoke forecast | ECCC FireWork WMS via MSC GeoMet | None | unlimited | WMS PNG / GRIB2 |
| 8 | Evacuation orders | BC Emergency Map ArcGIS FeatureServer | None | unlimited | GeoJSON |
| 9 | Climate historical + projections | ClimateData.ca + ECCC bulk CSV (Kamloops STN_ID 1163780) | None | unlimited | CSV/NetCDF |
| 10 | Globe terrain + imagery | Cesium Ion (World Terrain + OSM Buildings) + EOX Sentinel-2 cloudless | Free Ion token | 15 GB/mo streaming | 3D Tiles / WMTS |
| 11 | NDVI vegetation health | Google Earth Engine non-commercial | Google login | generous research tier | XYZ tiles / GeoTIFF |

**Three required free signups** before phase 1 can complete:
1. Cesium Ion access token (https://ion.cesium.com)
2. NASA FIRMS MAP_KEY (https://firms.modaps.eosdis.nasa.gov/api/map_key)
3. WAQI/AQICN token (https://aqicn.org/data-platform/token/)

Optional: Google Earth Engine signup (only if Phase 2 stretch goal of NDVI overlay is pursued).

---

## 3. Phase Map

| Phase | Title | Duration | Output you can demo |
|---|---|---|---|
| **0** | Foundation, design system, monorepo scaffold | ~1 sitting | Empty but beautifully styled shell with dark theme, design tokens, fonts loaded, FastAPI hello-world, Vite running on localhost:5173 |
| **1** ✅ | Data ingestion + ETL pipeline | shipped | 12 ingest jobs covering BC fires (current + 1999-2025 historical = 15,996 records), ERA5 + GEM-HRDPS weather, derived FWI, ECCC GeoMet AQHI, WAQI, FireWork smoke (73-step interval-expanded), BC evac, CMIP6 projections placeholder. DuckDB + SQLite + Parquet. |
| **2** ✅ | 3D Cesium globe + Wildfire Risk Map | shipped | Live 3D globe, 6 toggleable layers, glassmorphic LayerDetailModal with filterable scrollable list per layer (each row click → flyTo), LocationSearch with Cesium Ion geocoder, 4 camera presets (Globe/Region/Kamloops/TRU), live coordinate readout, ErrorBoundary, single-viewer architecture mounted at AppShell. |
| **3** ✅ | ML model — wildfire risk classifier | shipped | LightGBM trained on 8,394 days (1999-2021), val 2022, test 2023. PR-AUC 0.66 vs FWI-threshold 0.52 (+14.8 pts). Per-cell H3 r=5 risk grid (185 hexes), CFFDRS class comparison surfaced alongside ML output. Model card published. AQ forecaster moved to Phase 4. |
| **4** ✅ | Air Quality Monitor + 2nd ML model | shipped | **AQ forecaster**: 21 LightGBM quantile models (7 horizons × q10/q50/q90) trained on 92-day Open-Meteo CAMS hourly data + co-located weather. Beats persistence at 6+/12+/36+/48 h. **Dashboard**: AQHI dial, 48-h forecast chart with q10-q90 band, pollutant bars, AQHI stations minimap, 365-day smoke event calendar, Health Canada guidance with 3 audience tabs, AQHI threshold Web Notifications (localStorage). **Smoke time scrubber** on the globe (73 hourly timesteps from ECCC RAQDPS-FW WMS). |
| **5** | Community Preparedness Hub | 1-2 sittings | Neighbourhood selector, dynamic FireSmart checklist, evac status widget, points + achievements (localStorage) |
| **6** | Climate Trend Module | 1 sitting | 30-yr Thompson-Okanagan fire-season severity chart, projected temp/precip overlay, narrative annotations |
| **7** | Polish, performance, iPad/desktop optimization, demo | 1-2 sittings | 60 fps target, < 3s cold load, recorded 90s demo video, README + run instructions |

---

<!-- PHASES_BELOW -->

# Phase 0 — Foundation, Design System, Monorepo Scaffold

> **Goal**: stand up a beautiful empty shell. By the end of Phase 0, running `pnpm dev` and `uv run uvicorn ...` should give a localhost frontend with the locked design tokens, fonts loaded, dark tactical theme, an animated splash, and an FastAPI hello-world reachable from the browser. **Zero feature logic** — the visual personality must already be in place because every later phase sits inside it.

## 0.1 Repository scaffold

Create this exact tree at the project root:

```
WildFire-IQ/
├── apps/
│   ├── web/                      # React + Vite frontend
│   └── api/                      # FastAPI backend
├── packages/
│   ├── shared-types/             # TypeScript types co-generated from FastAPI OpenAPI
│   └── design-tokens/            # CSS variables + Tailwind preset, single source of design truth
├── data/
│   ├── raw/                      # Untouched API dumps (Parquet, GeoJSON)
│   ├── processed/                # Cleaned + joined datasets (Parquet)
│   ├── geo/                      # Static GeoJSON for Thompson-Okanagan boundaries
│   └── models/                   # Trained ML model artifacts (.pkl, .onnx, .json metadata)
├── notebooks/                    # Jupyter notebooks for EDA + model dev
├── scripts/
│   ├── ingest/                   # Standalone ingestion scripts (callable via `uv run`)
│   └── train/                    # Model training scripts
├── docs/
│   ├── data-dictionary.md
│   ├── model-cards/
│   └── api-keys-setup.md
├── .env.example                  # All required env vars documented
├── .gitignore
├── pnpm-workspace.yaml
├── package.json                  # Root, workspace runner
├── pyproject.toml                # uv-managed Python deps (root)
├── README.md
└── implementationplan.markdown   # this file
```

**Tasks**:
- Initialise `git init` if not already.
- `pnpm-workspace.yaml` with `apps/*` and `packages/*`.
- Root `package.json` with scripts: `dev` (concurrently runs web + api), `lint`, `format`, `test`, `build`.
- `pyproject.toml` at root for uv. Use uv workspaces (`[tool.uv.workspace]`) so `apps/api` and `scripts/` share env.
- Comprehensive `.gitignore` covering `node_modules/`, `.venv/`, `.env`, `data/raw/`, `data/processed/`, `*.pkl`, `*.onnx`, `dist/`, `.DS_Store`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, `cesium-static/`, etc. Do **not** gitignore `data/geo/` (small static reference layers belong in repo).
- `.env.example` listing: `CESIUM_ION_TOKEN`, `FIRMS_MAP_KEY`, `WAQI_TOKEN`, `VITE_API_BASE_URL=http://localhost:8000`, `DATABASE_URL=sqlite:///./data/wildfireiq.db`.

## 0.2 Design tokens (single source of truth)

Create `packages/design-tokens/tokens.css` with the **locked** palette and typography. Tailwind v4 reads CSS variables directly via `@theme`.

### Color system (HSL channels for compositing)

```css
:root {
  /* Base — deep tactical night */
  --color-bg-0: hsl(220 25% 4%);           /* page background, almost black */
  --color-bg-1: hsl(220 22% 7%);           /* card surfaces */
  --color-bg-2: hsl(220 20% 10%);          /* elevated surfaces, modals */
  --color-bg-3: hsl(220 18% 14%);          /* hover state */
  --color-stroke: hsl(220 15% 22%);        /* hairline borders */
  --color-stroke-strong: hsl(220 15% 32%);

  /* Text */
  --color-text-hi: hsl(40 30% 96%);        /* primary text, warm off-white */
  --color-text-mid: hsl(40 12% 72%);       /* secondary */
  --color-text-low: hsl(40 8% 50%);        /* tertiary, captions */

  /* Brand — ember spectrum (fire intensity scale) */
  --color-ember-50:  hsl(28 100% 95%);
  --color-ember-200: hsl(28 100% 78%);
  --color-ember-400: hsl(22 100% 60%);     /* fire accent */
  --color-ember-500: hsl(18 95% 54%);      /* primary CTA */
  --color-ember-600: hsl(14 92% 48%);
  --color-ember-700: hsl(8 88% 42%);       /* extreme risk */
  --color-ember-900: hsl(0 80% 30%);

  /* Risk scale (semantic, NOT decorative — these go on the map) */
  --risk-low:        hsl(140 55% 50%);     /* sage green */
  --risk-moderate:   hsl(45 95% 58%);      /* amber */
  --risk-high:       hsl(22 100% 56%);     /* fire orange */
  --risk-extreme:    hsl(0 88% 52%);       /* deep red */

  /* AQ scale (Canadian AQHI 1-10+ palette) */
  --aq-1: hsl(195 75% 55%);  --aq-2: hsl(180 65% 48%);  --aq-3: hsl(140 55% 50%);
  --aq-4: hsl(60 80% 55%);   --aq-5: hsl(40 90% 55%);   --aq-6: hsl(28 95% 55%);
  --aq-7: hsl(15 90% 55%);   --aq-8: hsl(0 80% 55%);    --aq-9: hsl(340 70% 50%);
  --aq-10: hsl(320 60% 40%); --aq-plus: hsl(280 50% 30%);

  /* Accent — cool counterpoint (data, calm states) */
  --color-cyan-glow: hsl(185 90% 55%);     /* used SPARINGLY, only for live data pulses */
  --color-violet:    hsl(265 60% 60%);     /* climate projections only */

  /* Typography */
  --font-display: 'Space Mono', 'JetBrains Mono', ui-monospace, monospace;
                  /* NOT chosen — see below: we override in 0.3 */
  --font-body:    'Geist', 'IBM Plex Sans', system-ui;
  --font-data:    'JetBrains Mono', ui-monospace, monospace;

  /* Spacing scale (4px base) */
  --space-1: 4px;  --space-2: 8px;  --space-3: 12px; --space-4: 16px;
  --space-5: 24px; --space-6: 32px; --space-7: 48px; --space-8: 64px;

  /* Radii */
  --radius-sm: 4px; --radius-md: 8px; --radius-lg: 14px; --radius-pill: 999px;

  /* Shadows + glow */
  --shadow-card: 0 1px 0 hsl(220 30% 15% / 0.6) inset, 0 12px 32px -16px hsl(0 0% 0% / 0.6);
  --glow-ember: 0 0 24px hsl(18 95% 54% / 0.45), 0 0 4px hsl(18 95% 54% / 0.9);
  --glow-cyan:  0 0 18px hsl(185 90% 55% / 0.4);

  /* Motion */
  --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in-out-quart: cubic-bezier(0.76, 0, 0.24, 1);
  --dur-fast: 180ms; --dur-base: 320ms; --dur-slow: 640ms; --dur-cinema: 1400ms;
}
```

### 0.3 Typography (locked, distinctive — frontend-design skill compliance)

**Banned per skill rules**: Inter, Roboto, Arial, generic system-ui as primary, Space Grotesk (skill explicitly calls it out as overused).

**Selected pairing — distinctive but production-trusted**:
- **Display**: `Migra` (Pangram Pangram, free for personal/research) **OR** `Boldonse` **OR** `Editorial New` (free trial). Recommended primary: **`PP Neue Machina`** (Pangram Pangram free for non-commercial) — geometric, technical, has the "tactical document" feel.
  - Free fallback if licensing is uncertain: **`Bricolage Grotesque`** (SIL Open Font License via Google Fonts) — variable, characterful, distinctly *not* Inter.
- **Body**: **`Geist Sans`** (MIT, Vercel) — clean but with personality. Backup: `IBM Plex Sans`.
- **Data/numerics**: **`JetBrains Mono`** (Apache 2.0). Used for every number on the screen — temperatures, AQI values, coordinates, timestamps. This is the visual signature.

Self-host the fonts under `apps/web/public/fonts/` to avoid Google Fonts CORS and keep the experience offline-capable. Generate a `@font-face` stylesheet in `packages/design-tokens/fonts.css`.

### 0.4 Tailwind v4 setup

`apps/web/src/app.css`:

```css
@import "tailwindcss";
@import "@wildfireiq/design-tokens/tokens.css";
@import "@wildfireiq/design-tokens/fonts.css";

@theme {
  --color-bg-0: var(--color-bg-0);
  --color-bg-1: var(--color-bg-1);
  /* ...remap all tokens into Tailwind's @theme... */
  --font-sans: var(--font-body);
  --font-mono: var(--font-data);
  --font-display: var(--font-display);
}

/* Global atmosphere — NOT optional */
html, body { background: var(--color-bg-0); color: var(--color-text-hi); font-family: var(--font-body); }
body::before {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 1;
  background-image: url('/textures/grain.png');
  opacity: 0.05; mix-blend-mode: overlay;
}
```

The grain overlay (PNG, 512×512, 5% opacity) is non-negotiable — it's the texture that separates this from a flat dashboard.

## 0.5 Frontend scaffold (apps/web)

Tasks:
- `pnpm create vite apps/web --template react-ts`.
- Install: `react@18 react-dom@18 react-router-dom@6 @tanstack/react-query@5 zustand motion resium cesium @visx/visx d3 plotly.js maplibre-gl tailwindcss@next @tailwindcss/vite`.
- Dev: `vitest @testing-library/react @testing-library/jest-dom @biomejs/biome typescript @types/cesium`.
- `vite.config.ts`: enable `@tailwindcss/vite` plugin; configure `cesium` static asset copying via `vite-plugin-static-copy` so `cesium/Build/Cesium/Workers`, `Assets`, `Widgets`, `ThirdParty` are served from `/cesium/` at runtime; set `define: { CESIUM_BASE_URL: JSON.stringify('/cesium/') }`.
- Set up React Router with placeholders for: `/` (globe / risk map), `/air-quality`, `/preparedness`, `/climate`, `/about`.
- Build the `<AppShell>` component: persistent left rail (icon nav), top status bar (live clock UTC + Kamloops local, current AQHI badge, fire count badge — all wired to `/api/*` later), and a centred slot for routes. The shell is glassmorphic (`backdrop-filter: blur(20px) saturate(1.4)`), with a 1px `--color-stroke` border, sitting *over* the Cesium canvas where applicable.
- Splash/intro: 1.4s animated logo reveal (Motion + GSAP) with a slow camera zoom-in over a still rendering of the Thompson-Okanagan terrain (use a static screenshot for now, replaced in Phase 2).
- Implement the `useReducedMotion` hook hookup so all GSAP / Motion timelines respect `prefers-reduced-motion`.

## 0.6 Backend scaffold (apps/api)

Tasks:
- `uv init apps/api --package`.
- `uv add fastapi 'uvicorn[standard]' httpx pydantic-settings sqlalchemy 'sqlalchemy[asyncio]' aiosqlite duckdb pandas numpy geopandas shapely apscheduler python-dotenv structlog`.
- Dev: `uv add --dev pytest pytest-asyncio httpx ruff mypy`.
- `apps/api/wildfireiq_api/main.py`: FastAPI app with CORS allowing `http://localhost:5173`, structured logging, `/healthz` returning `{"ok": true, "version": "0.1.0"}`, OpenAPI tags grouped by feature.
- `wildfireiq_api/settings.py` using `pydantic-settings` to read `.env` — type-safe config.
- `wildfireiq_api/db.py`: SQLAlchemy async engine + `get_session` dependency.
- Stub routers in `wildfireiq_api/routers/`: `fires.py`, `risk.py`, `aq.py`, `evac.py`, `climate.py`, `firesmart.py` — each returning `{"status": "not_implemented"}` for now so the URL contract is locked.
- Auto-generate TypeScript types: a script `pnpm gen:types` that hits `http://localhost:8000/openapi.json` and runs `openapi-typescript` to emit `packages/shared-types/api.d.ts`. Frontend imports types from there — no drift.

## 0.7 Cesium bootstrap (smoke test only)

Phase 0 ends when `/` renders an empty Cesium `Viewer` over the Thompson-Okanagan with:
- Cesium World Terrain enabled (Ion token from env).
- Sentinel-2 cloudless 2024 (EOX) as the imagery layer.
- Camera initial position: `Cesium.Cartesian3.fromDegrees(-120.3273, 50.6745, 180000)`, `heading: 0, pitch: -45°, roll: 0`.
- Default UI widgets disabled: no toolbar, geocoder, home button, base layer picker, animation widget, timeline (we'll build our own in Phase 2).
- Sky atmosphere on, fog enabled and tuned for *moodier* night-side, `viewer.scene.globe.enableLighting = false` (we want our tactical look, not realistic day/night).

This is enough to verify the full toolchain works end-to-end before any feature work.

## 0.8 Verification (must pass before Phase 1)

- [ ] `pnpm dev` opens `http://localhost:5173` showing the splash → AppShell with the dark tactical theme, fonts loaded (verify via DevTools network tab — no Google Fonts requests, all `/fonts/*.woff2`), grain overlay visible.
- [ ] Cesium globe renders the Thompson-Okanagan with Sentinel-2 imagery and terrain elevation.
- [ ] No console warnings from Cesium or React.
- [ ] `curl http://localhost:8000/healthz` returns `{"ok": true, ...}`.
- [ ] `curl http://localhost:8000/openapi.json` is valid; `pnpm gen:types` produces `packages/shared-types/api.d.ts`.
- [ ] Lighthouse desktop run on `/` ≥ 90 Performance, ≥ 95 Accessibility (page is mostly empty so this should be free).
- [ ] iPad Pro 12.9" simulator (Safari Tech Preview): globe pans/zooms at ≥ 50 fps with two-finger gestures.

## 0.9 Deliverable

A repository in which **only the empty shell** is built — but it already feels distinctive, fast, and intentional. **A future you stops here for 30 seconds and feels excited to keep building.**

# Phase 1 — Data Ingestion & ETL Pipeline

> **Goal**: every dataset the app will ever need is downloaded, cleaned, joined, and served from `apps/api` over JSON. ML training in Phase 3 can run with no internet. The frontend in Phase 2 can render real fires, real weather, real AQ, real evacuation orders. This phase is the longest and most consequential — get it right and everything afterwards is just presentation.

## 1.1 Bounding box & static reference geometry

Before any ingestion, define the canonical region. Create `data/geo/` with these GeoJSON files:

- **`thompson_okanagan.geojson`** — outer working bbox. Polygon: `[-121.5, 50.0]` to `[-118.5, 51.5]` (covers Kamloops, Vernon, Kelowna, Salmon Arm, Merritt, Logan Lake, Sun Peaks, Falkland).
- **`kamloops_city.geojson`** — Kamloops municipal boundary, downloaded once from DataBC (`WHSE_LEGAL_ADMIN_BOUNDARIES.ABMS_MUNICIPALITIES_SP`, filter `MUNICIPALITY_NAME = 'Kamloops'`). Static, in repo.
- **`kamloops_neighbourhoods.geojson`** — neighbourhood polygons for the Phase 5 prep hub (Aberdeen, Sahali, Brocklehurst, North Shore, Westsyde, Valleyview, Juniper Ridge, Dallas, Barnhartvale, Pineview Valley, Batchelor Heights, Dufferin, Knutsford, Rayleigh). Source: City of Kamloops Open Data (`kamloopsdata.opendata.arcgis.com`). If a single layer doesn't exist, hand-construct from postal-code clusters or census tracts. Acceptable to ship a manually curated 14-feature GeoJSON.
- **`fire_centres.geojson`** — Kamloops Fire Centre boundary from BC Wildfire Service (DataBC `WHSE_ADMIN_BOUNDARIES.DRP_FIRE_CENTRES_SP`).

A constant `BBOX = (-121.5, 50.0, -118.5, 51.5)` lives in `apps/api/wildfireiq_api/constants.py` and is the single filter every ingest job applies.

## 1.2 Storage layout

```
data/
├── raw/
│   ├── databc_fires_current/YYYY-MM-DDTHH/*.geojson      # 15-min snapshots
│   ├── databc_fires_historical/by_year/YYYY.parquet
│   ├── firms_hotspots/YYYY-MM-DD.parquet
│   ├── open_meteo/YYYY-MM-DD.parquet                     # daily Kamloops snapshot
│   ├── eccc_climate_kamloops/YYYY.csv                    # ECCC bulk per year
│   ├── cwfis_fwi/YYYY-MM-DD.geojson                      # daily FWI station table
│   ├── geomet_aqhi/YYYY-MM-DDTHH.geojson                 # hourly
│   ├── waqi_kamloops/YYYY-MM-DDTHH.json
│   ├── firework_smoke/YYYY-MM-DDTHH/*.png                # WMS tile cache, optional
│   ├── evac_bcem/YYYY-MM-DDTHH.geojson
│   └── climatedata_projections/{ssp126,ssp245,ssp585}.csv
├── processed/
│   ├── fires_unified.parquet            # 1999–today, single schema
│   ├── weather_kamloops_daily.parquet
│   ├── fwi_kamloops_daily.parquet
│   ├── aq_kamloops_hourly.parquet
│   ├── evac_active.parquet
│   └── climate_normals.parquet
└── wildfireiq.db                        # SQLite — operational/cache; analytics live in DuckDB
```

## 1.3 Ingestion job framework

Build `apps/api/wildfireiq_api/ingest/base.py`:

```python
class IngestJob(Protocol):
    name: str                          # "databc_fires_current"
    cadence: str                       # APScheduler cron expression
    async def run(self, ctx: IngestContext) -> IngestReport: ...
```

Every job:
1. Fetches with `httpx.AsyncClient` and a polite `User-Agent: WildfireIQ/0.1 (research; deeparsh@<>; +https://...)`.
2. Validates with Pydantic models — bad rows are quarantined to `data/raw/<job>/_rejected/` not silently dropped.
3. Writes raw to `data/raw/<job>/...` (Parquet wherever possible).
4. Updates `processed/*.parquet` via DuckDB upserts.
5. Logs structured JSON to stdout + `data/logs/ingest.jsonl`.
6. Records its run + row count + duration in SQLite table `ingest_runs`.

Retry with `tenacity` (exponential backoff, max 3). All upstream calls cached by URL+date in SQLite for 6 h to avoid re-hitting during dev.

## 1.4 The eleven jobs (full catalogue)

### Job 1 — `databc_fires_current` (every 15 min)
- WFS: `https://openmaps.gov.bc.ca/geo/pub/wfs?service=WFS&version=2.0.0&request=GetFeature&typeName=pub:WHSE_LAND_AND_NATURAL_RESOURCE.PROT_CURRENT_FIRE_POLYS_SP&outputFormat=application/json&BBOX=-121.5,50.0,-118.5,51.5,EPSG:4326`
- And the points layer `PROT_CURRENT_FIRE_PNTS_SP`.
- Normalise schema → `(fire_id, name, status, stage_of_control, hectares, discovery_date, geometry)`.

### Job 2 — `firms_hotspots` (every 30 min)
- USFS NRT endpoint: `https://firms.modaps.eosdis.nasa.gov/usfs/api/area/csv/{MAP_KEY}/VIIRS_NOAA20_NRT/-121.5,50.0,-118.5,51.5/3` and same for `VIIRS_SNPP_NRT`, `MODIS_NRT`.
- Parse CSV with PapaParse-equivalent `csv.DictReader`. Drop low-confidence (<30) points.
- Output: `(latitude, longitude, acq_datetime_utc, brightness, frp, confidence, source, daynight)`.

### Job 3 — `databc_fires_historical` (one-time bootstrap, then yearly refresh)
- Bulk download `https://catalogue.data.gov.bc.ca/dataset/fire-perimeters-historical` GeoJSON.
- Bulk download `https://catalogue.data.gov.bc.ca/dataset/fire-incident-locations-historical`.
- Filter to BBOX, normalise, write `data/raw/databc_fires_historical/by_year/YYYY.parquet`. **At minimum 1999 → present** (proposal commitment); aim for **1950 → present** since the data exists.
- This single job is the spine of the wildfire risk model.

### Job 4 — `open_meteo_kamloops_daily` (hourly during build, daily in prod)
- `https://api.open-meteo.com/v1/forecast?latitude=50.6745&longitude=-120.3273&current=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m,precipitation,vapour_pressure_deficit&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,precipitation,vapour_pressure_deficit,et0_fao_evapotranspiration&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,et0_fao_evapotranspiration&past_days=2&forecast_days=10&timezone=America/Vancouver&models=gem_hrdps_continental`.
- For training, also pull historical reanalysis: `https://archive-api.open-meteo.com/v1/archive?latitude=50.6745&longitude=-120.3273&start_date=1999-01-01&end_date=<yesterday>&daily=...&hourly=...&timezone=America/Vancouver`. ERA5 backed, no key, ideal for model training.

### Job 5 — `eccc_climate_kamloops_bulk` (one-time bootstrap)
- Loop years 1995–current: `https://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID=1163780&Year={YYYY}&Month=1&timeframe=2`.
- Concatenate, normalise column names, write `data/processed/weather_kamloops_daily.parquet`.
- Used as ground truth for cross-validating Open-Meteo archive data.

### Job 6 — `cwfis_fwi_daily` (daily, 18:00 PST after observation cycle)
- WFS: `https://cwfis.cfs.nrcan.gc.ca/geoserver/public/ows?service=WFS&version=2.0.0&request=GetFeature&typeName=public:fwi_stns_current&outputFormat=application/json&bbox=-121.5,50.0,-118.5,51.5`.
- Parse station table → `(station_name, station_id, ffmc, dmc, dc, isi, bui, fwi, dsr, observation_date)`.
- For **historical FWI** (model training): backfill via the cffdrs Python port (`cffdrs-py`) computed from the Open-Meteo archive (noon-LST temp, RH, wind, precip). Validate against any CWFIS-published historical files.

### Job 7 — `geomet_aqhi_realtime` (hourly)
- `https://api.weather.gc.ca/collections/aqhi-observations-realtime/items?bbox=-121.5,50.0,-118.5,51.5&f=json&datetime=<last-2-hours>`.
- Stations of interest: `aqhi_id` for "Kamloops Aberdeen", "Kamloops Brocklehurst", "Kamloops Mission Flats", "Vernon Science Centre", "Penticton".

### Job 8 — `waqi_kamloops` (hourly, backup)
- `https://api.waqi.info/feed/kamloops/?token={WAQI_TOKEN}` plus `geo:50.67;-120.33` neighbours.
- Acts as cross-check for ECCC and provides PM2.5/PM10/O3/NO2 component split when ECCC only gives composite AQHI.

### Job 9 — `firework_smoke_forecast` (every 6 h, runs after 00Z and 12Z)
- WMS GetMap PNG cache for `RAQDPS-FW.SFC_PM2.5` over BBOX, 13 timesteps × 3-hour intervals = 39-hour forecast.
- For numeric values (needed by the Phase 4 forecast comparison): pull GRIB2 from `https://dd.weather.gc.ca/model_raqdps-fw/10km/grib2/<RUN>/<HHH>/`, decode with `cfgrib`/`pygrib`, sample at Kamloops lat/lon, store hourly PM2.5 µg/m³.

### Job 10 — `bcem_evacuations` (every 5 min during fire season, hourly otherwise)
- ArcGIS FeatureServer query: `https://services6.arcgis.com/ubm4tcTYICKBpist/arcgis/rest/services/Evacuation_Orders_and_Alerts/FeatureServer/0/query?where=1=1&outFields=*&f=geojson` (verify the layer ID at start of fire season — it has historically changed).
- Filter geometry intersecting BBOX. Schema: `(event_id, status [Order/Alert/Rescind], issuing_authority, issued_utc, area_name, geometry)`.
- Backup: parse EmergencyInfoBC RSS (`https://www.emergencyinfobc.gov.bc.ca/feed/`) for free-text events, run a small regex extractor.

### Job 11 — `climatedata_ca_projections` (one-time bootstrap)
- Pull SSP1-2.6, SSP2-4.5, SSP5-8.5 CMIP6 ensembles for Kamloops grid cell (lat 50.67, lon -120.33), variables: `tasmax`, `tasmin`, `pr`, fire-weather-relevant `vpd`. Endpoint pattern from `data.climatedata.ca` download API.
- Output: tidy CSV `(year, ssp, variable, value, ensemble_quantile)` for the Phase 6 chart.

### Optional — `gee_ndvi_thompson_okanagan` (weekly, Phase 2 stretch)
- Earth Engine job exporting NDVI composite as XYZ tiles. Skip if signup friction is not worth it.

## 1.5 Data joining & feature engineering (DuckDB)

Once raw files exist, build `apps/api/wildfireiq_api/etl/build_features.py`:

```sql
-- Daily fire occurrence target (1 if any fire ignited in any cell on this day, else 0)
CREATE TABLE fire_days AS
SELECT date_trunc('day', discovery_date) AS day, h3_cell_index_8 AS cell, COUNT(*) AS n_fires
FROM read_parquet('data/raw/databc_fires_historical/by_year/*.parquet')
GROUP BY 1, 2;

-- Daily Kamloops weather + FWI feature row
CREATE TABLE features_daily AS
SELECT w.day, w.cell,
       w.temp_max, w.temp_min, w.rh_min, w.wind_max, w.precip_sum, w.vpd_max, w.dry_spell_days,
       f.ffmc, f.dmc, f.dc, f.isi, f.bui, f.fwi, f.dsr,
       n.ndvi_anomaly_30d
FROM weather_kamloops_daily w
LEFT JOIN fwi_kamloops_daily f USING (day)
LEFT JOIN ndvi_anomaly n USING (day, cell);
```

H3 hexagonal binning at resolution 8 (~0.7 km² cells) for the wildfire risk model. The Thompson-Okanagan BBOX yields ~12,000 cells — tractable for tabular ML.

Engineered features (used in Phase 3 model):
- 7-day, 14-day, 30-day rolling means of temp_max, precip, RH min, wind max.
- Dry-spell length (consecutive days with `precip < 1mm`).
- Day-of-year sine/cosine encoding.
- Year-on-year FWI anomaly.
- NDVI anomaly vs 5-yr median (if NDVI ingested).
- Distance to nearest historical fire centroid in last 5 yrs.
- Population density in cell (Statistics Canada grid, one-time download).
- Land cover class (Canada AAFC ACGEO 2020).
- Elevation, slope, aspect (Cesium World Terrain → derive once via `gdaldem`, store per cell).

## 1.6 API surface (frozen contract for the frontend)

Every endpoint returns `application/json` with a top-level `{ data, meta }` envelope. `meta.cached_at`, `meta.source`, `meta.attribution`. Use FastAPI response models so OpenAPI is exact.

```
GET  /api/fires/current?bbox=...                  → list[FireFeature]
GET  /api/fires/hotspots?since=24h                → list[Hotspot]
GET  /api/fires/historical?year=2003              → list[HistoricalFire]
GET  /api/risk/today?cell=<h3>                    → RiskScore           (Phase 3)
GET  /api/risk/grid                               → list[RiskCell]      (Phase 3, all cells)
GET  /api/aq/current                              → AqhiNow
GET  /api/aq/forecast?hours=48                    → list[AqhiForecast]  (Phase 3)
GET  /api/aq/history?days=30                      → list[AqhiPoint]
GET  /api/weather/current                         → WeatherSnapshot
GET  /api/weather/forecast?hours=72               → list[WeatherPoint]
GET  /api/fwi/today                               → FwiSnapshot
GET  /api/evac/active                             → list[EvacZone]
GET  /api/evac/check?lat=&lon=                    → EvacStatus
GET  /api/firesmart/checklist?neighbourhood=      → list[ChecklistItem] (Phase 5)
GET  /api/climate/seasonal?metric=area_burned     → list[YearlyMetric]  (Phase 6)
GET  /api/climate/projection?ssp=245&var=tasmax   → list[ProjectionPoint] (Phase 6)
```

## 1.7 Scheduler

`apps/api/wildfireiq_api/scheduler.py` wires APScheduler at app startup:

| Job | Cron |
|---|---|
| `databc_fires_current` | `*/15 * * * *` |
| `firms_hotspots` | `*/30 * * * *` |
| `open_meteo_kamloops_daily` | `5 * * * *` (top of hour + 5 min) |
| `cwfis_fwi_daily` | `0 18 * * *` PST |
| `geomet_aqhi_realtime` | `10 * * * *` |
| `waqi_kamloops` | `25 * * * *` |
| `firework_smoke_forecast` | `0 */6 * * *` |
| `bcem_evacuations` | `*/5 * * * *` Apr-Oct, `0 * * * *` Nov-Mar |

Bootstrap jobs (historical fires, ECCC climate bulk, climate projections) run only once via `uv run python scripts/ingest/bootstrap.py`.

## 1.8 Verification

- [ ] `uv run python scripts/ingest/bootstrap.py` completes; `data/processed/fires_unified.parquet` has ≥ 25,000 rows spanning 1999–today.
- [ ] `weather_kamloops_daily.parquet` has ≥ 9,000 daily rows (≥ 25 yrs).
- [ ] Calling each `/api/*` endpoint returns valid JSON conforming to the OpenAPI schema.
- [ ] `pytest apps/api/tests/test_ingest.py` — fixtures with mocked HTTP responses validate every parser.
- [ ] DuckDB query `SELECT COUNT(DISTINCT cell), COUNT(DISTINCT day) FROM features_daily` returns ≥ 12,000 cells × 9,000 days.
- [ ] Scheduler logs show first successful runs of all 8 recurring jobs.
- [ ] No API key has ever been logged or persisted to disk outside `.env`.

## 1.9 Deliverable

A backend that already serves the entire app's data — even though no frontend feature is built yet. Anyone can `curl` real fires, real weather, real evacuation orders, real 25-yr historical fire records, right now, locally.

# Phase 2 — 3D Cesium Globe + Wildfire Risk Map (Feature 1)

> **Goal**: the centrepiece. A breathtaking 3D Cesium globe of the Thompson-Okanagan that opens with a cinematic camera fly-in, layers in current fires, FIRMS hotspots, FWI heatmap, evacuation polygons, and (after Phase 3) the AI risk grid. Every interaction feels deliberate and 60 fps. This is the screen people screenshot.

## 2.1 Globe configuration

Build `apps/web/src/features/globe/WildfireGlobe.tsx` using **Resium**. Configuration:

- **Terrain**: `Cesium.createWorldTerrainAsync({ requestVertexNormals: true, requestWaterMask: false })`. Vertex normals are required for the cinematic shading we'll apply.
- **Imagery base layer**: EOX Sentinel-2 cloudless 2024 — `new Cesium.WebMapTileServiceImageryProvider({ url: 'https://tiles.maps.eox.at/wmts', layer: 's2cloudless-2024_3857', style: 'default', tileMatrixSetID: 'g', maximumLevel: 17, credit: '...' })`.
- **High-zoom imagery** (loaded only when `camera.positionCartographic.height < 12000`): Bing Maps Aerial via Ion (`Cesium.IonImageryProvider({ assetId: 2 })`). This swap keeps streaming meter low.
- **3D buildings**: Cesium OSM Buildings as `Cesium.Cesium3DTileset.fromIonAssetId(96188)`. Stylise: extruded blocks tinted near-black (`color: color('hsl(220, 22%, 7%)')`) with a thin amber rim light via custom `silhouette` post-process.
- **Atmosphere**: keep `scene.skyAtmosphere` on, set `hueShift = -0.08`, `saturationShift = -0.3`, `brightnessShift = -0.15` for the moody tactical look.
- **Lighting**: `globe.enableLighting = false`. Replace with a custom directional light pinned at azimuth 230°, elevation 20° (warm sunset side-light). Implement via a Cesium post-process stage that layers an orange-tinted lambert pass.
- **Fog**: `scene.fog.density = 1.5e-4`, `scene.fog.minimumBrightness = 0.02`. Fog keeps the horizon soft and tactical-looking.
- **Sun/Moon/Stars**: hidden (`scene.sun.show = false`, `scene.moon.show = false`, `scene.skyBox.show = false`) — replaced with a custom **starfield CSS layer** behind the canvas for design control.
- **Performance**: `viewer.scene.postProcessStages.fxaa.enabled = true`, `viewer.scene.requestRenderMode = true`, `viewer.scene.maximumRenderTimeChange = Infinity`. Render-on-demand drops idle GPU usage by 90%.

## 2.2 Cinematic intro

When `/` first loads, run a GSAP timeline:

1. **0.0s**: black overlay covers viewport, AppShell faded out, splash logo centred.
2. **0.6s**: starfield fades in behind logo.
3. **1.2s**: logo eases out; black overlay fades to 0; reveal globe at far distance (`height: 8,000,000 m`, looking down on western Canada).
4. **1.4s → 4.4s**: `viewer.camera.flyTo({ destination: ..., duration: 3.0, easingFunction: EasingFunction.QUINTIC_IN_OUT })` to canonical Thompson-Okanagan view (`-120.3273, 50.6745, 180,000 m`, pitch -45°, heading 12°).
5. **3.0s** (parallel): AppShell glassmorphic chrome fades in (left rail slides in from `x: -32px`, top bar from `y: -16px`).
6. **4.4s**: layers begin streaming — fires pop in with a brief amber flash + scale punch (`scale: 0 → 1.2 → 1.0`, 320ms each), staggered 40ms apart.

Honour `prefers-reduced-motion` — collapse to a 400ms fade-cut.

## 2.3 Layers (toggleable via left rail)

Each layer is a `LayerSpec` with `{ id, name, icon, defaultOn, source, render }`:

### Layer A — **Active Fires** (default ON)
- Fetch `/api/fires/current` via TanStack Query, refetch every 60 s.
- Render perimeters as `GroundPolylinePrimitive` with material `PolylineGlowMaterialProperty({ glowPower: 0.25, color: var(--color-ember-500) })`, plus filled `GroundPrimitive` at 35% opacity.
- Render fire points as `BillboardCollection` using a custom SVG icon (an animated ember pulse, 3-frame loop).
- Click → side panel slides in with: name, hectares, status, discovery date, distance from Kamloops, link to BC Wildfire Service incident page.

### Layer B — **Satellite Hotspots (FIRMS)** (default ON)
- Fetch `/api/fires/hotspots?since=24h`. Each hotspot = `PointPrimitive` with size scaled by FRP (Fire Radiative Power), colour mapped from `--color-ember-200` → `--color-ember-700`.
- Animate appearance: spawn with `scale 0 → 1.4 → 1`, staggered. New hotspots from polling pulse for 6 s before settling.
- Tooltip on hover: "VIIRS NOAA-20 · 14:32 UTC · FRP 38.2 MW · confidence 88%".

### Layer C — **Risk Grid** (default OFF until Phase 3 ships)
- H3 r=8 cells over BBOX. Filled `GroundPrimitive` colour-coded by `risk_class`: `--risk-low` → `--risk-extreme`, opacity 0.45.
- Rendering: build a single `Primitive` with per-instance colour to avoid 12,000 entities (entities crash above ~50k triangles per the Cesium community guidance — primitives are the only way).
- Time scrubber widget at the bottom centre lets you sweep across the past 14 days + next 7 forecast days. Driven by `viewer.clock`.

### Layer D — **FWI Stations** (default OFF)
- Symbolised station points sized by FWI value, with mini bar-chart billboard showing FFMC/DMC/DC/ISI/BUI/FWI on hover.

### Layer E — **Evacuation Orders/Alerts** (default ON during fire season)
- Polygons from `/api/evac/active`. Order = `--risk-extreme` 25% opacity with 2px solid stroke; Alert = `--risk-high` 15% opacity with 2px dashed stroke.
- Animated diagonal hatch shader inside polygons (custom Material) so they read as caution-tape from a distance.

### Layer F — **Smoke Plume Forecast** (default OFF, opt-in)
- WMS PNG tiles from FireWork RAQDPS-FW.SFC_PM2.5 layered as `WebMapServiceImageryProvider` with `parameters: { transparent: true, format: 'image/png' }` and a custom colour ramp.
- Time-controlled by the same scrubber as Layer C.

### Layer G — **Wind Field** (default OFF, polish)
- Animated wind particles using `WebGLWindLayer` (port of `mapbox-wind-js` to Cesium). Renders ~6,000 particles flowing along the 10m wind grid from Open-Meteo HRDPS.

## 2.4 Side panels (glassmorphic)

- **Right panel**: detail/inspect. Slides in 280ms when a fire/hotspot/evac zone is clicked. Uses `position: absolute; right: 16px; top: 80px; bottom: 16px; width: 380px;` and `backdrop-filter: blur(28px) saturate(1.6); background: hsl(220 22% 7% / 0.72); border: 1px solid var(--color-stroke);`.
- **Left rail**: layer toggles. Each toggle row shows: icon, name, live count badge (e.g., "Active fires · 12"), and an on/off switch. Hovering a toggle dims all *other* layers to 25% opacity for 1.2s — a subtle "spotlight" effect.
- **Bottom centre**: time scrubber. Hidden until the user enables a time-driven layer (C or F).

## 2.5 Camera presets

A small camera preset bar lets the user snap to:
- "Region" — Thompson-Okanagan overview.
- "Kamloops" — city-level, height 8,000 m.
- "TRU campus" — height 1,500 m, pitch -25°, heading 240° (looking from south-east toward campus).
- "Fire of interest" — auto-bind to the largest active fire.

Each preset is a 1.6 s GSAP-driven `flyTo` with `EasingFunction.QUINTIC_IN_OUT`.

## 2.6 Performance targets & rules

- Single Cesium `Viewer` instance for the whole app (mounted at root, hidden via CSS when on non-globe routes — never unmounted).
- No more than **one** entity collection per layer; everything else is primitives.
- All `requestRender()` calls are gated by `requestRenderMode = true`.
- BillboardCollections share atlases; SVG icons pre-rasterised at 2x for retina at build time.
- Throttle hover interactions to ≤ 30 Hz with `lodash.throttle`.
- iPad Pro M2 target: ≥ 50 fps with all default layers on. Desktop with discrete GPU: 60 fps locked.

## 2.7 Accessibility

- Every layer toggle reachable by keyboard with focus rings using `--color-ember-400` outline at 2px offset.
- Side panels announce via `aria-live="polite"` when new content loads.
- A "data table view" toggle in the top bar offers an accessible HTML-table fallback of the same fires/hotspots/evac data — required for the proposal's public-good framing.

## 2.8 Verification

- [ ] Cold load → globe visible with current fires within 4 s on desktop (cable internet).
- [ ] All seven layers can be toggled; performance budget holds (frame time < 18 ms with everything on).
- [ ] Clicking a fire opens the right panel with correct attribution.
- [ ] Time scrubber moves the risk grid backward/forward in time without a frame skip.
- [ ] iPad Pro 12.9" (Safari Tech Preview): pan/zoom is smooth; touch hit targets ≥ 44 px on rail toggles.
- [ ] Reduced motion: intro is replaced by a 400 ms fade. Verified via DevTools rendering pane.
- [ ] Lighthouse Performance ≥ 80 on the globe page (Cesium is heavy — anything ≥ 80 with full WebGL counts as a win).

## 2.9 Deliverable

The first screenshot you can post that makes someone go *"wait — a student built this?"* The Wildfire Risk Map is alive with real data; only the AI-derived risk colouring still says "model not trained yet" (that's Phase 3).

# Phase 3 — Machine Learning Models (Wildfire Risk + 48-hour Air Quality)

> **Goal**: two real, defensible, validated models trained on the historical corpus from Phase 1. Both models produce calibrated probabilities with held-out validation against the **2022 + 2023** fire seasons (per proposal commitment). Outputs are served from `/api/risk/*` and `/api/aq/forecast`. Each model has a model card in `docs/model-cards/`.

## 3.1 Model 1 — Wildfire Risk Classifier

### Problem framing
> "Given features observed at the start of day D for cell C, predict P(at least one ignition in cell C between D 06:00 PST and D+1 06:00 PST)."

Multi-class output is then bucketed into the four-level risk scale the UI consumes:
- `Low`: P < 0.05
- `Moderate`: 0.05 ≤ P < 0.20
- `High`: 0.20 ≤ P < 0.50
- `Extreme`: P ≥ 0.50

(Thresholds are calibrated against historical class balance; document the exact cutoffs in the model card after isotonic calibration.)

### Training data
- **Spatial unit**: H3 r=8 cell. ~12,000 cells over BBOX.
- **Temporal range**: Apr 1 – Oct 31 of years 1999–2021 for **train + val**; 2022 + 2023 entirely held out for **test**.
- **Positive examples**: cell-days where ≥ 1 fire ignited (from `fires_unified.parquet`).
- **Negative examples**: random sample of cell-days with no ignition; downsample to ~5:1 negative:positive ratio so the dataset stays tractable.
- Total expected size: ~3M rows × 50 features.

### Features (computed in Phase 1's DuckDB pipeline)
- **Weather (lagged)**: temp_max, temp_min, RH_min, wind_max, gust_max, precip_sum, VPD_max, ET₀ — for D, D-1, D-2 + 7-day, 14-day, 30-day rolling means.
- **FWI**: FFMC, DMC, DC, ISI, BUI, FWI, DSR — for D, D-1, plus 30-day max.
- **Drought**: dry-spell length, days-since-last-rain ≥ 5mm, days-since-last-rain ≥ 1mm.
- **Phenology**: NDVI (cell mean) + NDVI anomaly vs 5-yr same-day median (only if Earth Engine layer was ingested).
- **Static (per-cell)**: elevation, slope, aspect, dominant land-cover class one-hot (forest/grass/agriculture/urban/water), distance-to-road, distance-to-historical-fire-centroid (5-yr), population density.
- **Calendar**: DOY sin/cos, year (for trend), is_weekend (human-ignition signal).
- **Lightning** (stretch): if Environment Canada CLDN lightning data available, add 24-hour strike count in cell.

### Algorithm choice
**Primary: gradient-boosted trees (LightGBM)**.
- Handles mixed types, non-linearity, missing values.
- Trains on a CPU laptop in minutes.
- Output probabilities are well-calibrated after Platt/isotonic.

Hyperparameters (start, then tune via Optuna 30 trials):
- `objective='binary'`, `num_leaves=63`, `max_depth=-1`, `learning_rate=0.05`, `feature_fraction=0.8`, `bagging_fraction=0.8`, `min_data_in_leaf=200`, `lambda_l2=1.0`, `n_estimators=2000` with `early_stopping_rounds=100` against val.

**Alternative**: XGBoost (similar perf) or a small MLP if features get rich enough. **Do not** use logistic regression as final model — it underperforms here.

### Validation strategy
- **Spatial-temporal CV**: 5 folds where each fold holds out a **set of years** (so 2018-2019 as one val fold, etc.), preventing leakage where the same cell appears in train+val on adjacent days.
- **Test (frozen)**: 2022 + 2023 in entirety. Reported metrics use this set ONLY.
- Metrics: **PR-AUC (primary)** because of class imbalance, ROC-AUC, Brier score (calibration), and "spatial Brier" — Brier averaged within each H3 cell to confirm geographic generalisation.
- **Calibration**: fit isotonic regression on val fold predictions; apply to test.
- **Baselines** to beat: (a) FWI threshold (`FWI > 19 → High`), (b) climatological frequency per cell-DOY. The model must outperform both on PR-AUC by a margin we report.

### Inference & serving
- After training, persist as `data/models/wildfire_risk_v1.pkl` + `wildfire_risk_v1.onnx` (via `onnxmltools`).
- FastAPI loads the ONNX model at startup with `onnxruntime`.
- `/api/risk/grid?date=2026-05-09` returns ~12,000 cells with `{cell_h3, risk_class, p, top_features}`.
- `top_features`: SHAP top-3 features for that cell-day (computed once per request via `shap.TreeExplainer` cached for the day).
- Daily batch job at 06:00 PST precomputes the entire grid and stores it in DuckDB so the GET is a SELECT, not a model run.

### Forecast horizon
The same model is run with **forecasted weather** (Open-Meteo HRDPS) to produce **next-7-day** risk grids. Each future day reuses the model — only the weather inputs change. Document forecast skill degradation by horizon in the model card.

## 3.2 Model 2 — 48-hour Air Quality Forecaster (Kamloops)

### Problem framing
> "Given hourly observations of AQHI/PM2.5 in Kamloops up to time T, plus current fire activity within 250 km, plus 48-hour weather forecasts (wind, mixing height proxy, precip, RH), predict hourly PM2.5 (µg/m³) for T+1 through T+48 hours."

The Phase 4 UI shows AQHI but PM2.5 is the regression target — convert PM2.5 → AQHI via the standard Health Canada formula at display time.

### Training data
- **Target**: hourly PM2.5 (µg/m³) at the Kamloops Aberdeen station (primary), with Brocklehurst as backup. Pulled from BC Air Data Archive bulk CSVs (ingested in Phase 1).
- **Range**: 2010 → 2021 for train+val; 2022+2023 held out.
- **Per-row features**:
  - Recent AQ: PM2.5 lags at T, T-1, T-3, T-6, T-12, T-24.
  - Fire activity: count + total FRP within 50 km, 100 km, 250 km of Kamloops in last 24 h (from FIRMS historical archive).
  - Wind: 10 m wind speed/direction at Kamloops + at the centroid of nearby active-fire cluster, projected as `wind_alignment = cos(bearing_to_fire − wind_dir)`.
  - Mixing height proxy: VPD, surface temp inversion proxy (T_sfc − T_850hPa from ERA5).
  - Precipitation in last 6 h.
  - Hour-of-day sin/cos, DOY sin/cos.

### Algorithm choice
**Primary: temporal gradient-boosted regression** — separate **LightGBM regressors per horizon h** (h ∈ {+1, +3, +6, +12, +24, +36, +48}) with `quantile` objective for each of `q=[0.1, 0.5, 0.9]`. This gives predictive intervals (the UI will render the 10-90 band as a soft glow around the forecast line).
- Why per-horizon: avoids the recurrent error compounding of a sequence model and trains fast.
- Quantile loss (`objective='quantile'`, `alpha=0.5/0.1/0.9`) is critical because the UI must show uncertainty during smoke events.

**Alternative**: a small Temporal Fusion Transformer (`pytorch-forecasting`) — only build if time and validation set say it materially beats LightGBM. **Don't** start there.

### Validation strategy
- Time-series CV (sliding window): train on 2010-2017, val 2018, then 2010-2018→2019, etc.
- Test: 2022 + 2023 hourly.
- Metrics: **MAE (µg/m³)**, **RMSE**, **pinball loss for q=0.1 and q=0.9**, **categorical AQHI accuracy** (does the predicted PM2.5 land in the right AQHI bucket?). Report stratified by AQHI level — performance during 7+ events matters most.
- Baselines: (a) persistence (PM2.5 at T+h = PM2.5 at T), (b) climatology by DOY+hour, (c) ECCC FireWork RAQDPS-FW PM2.5 sampled at Kamloops.

### Inference & serving
- Model artifacts in `data/models/aq_forecaster_v1/{h+1,h+3,...,h+48}.pkl`.
- `/api/aq/forecast?hours=48` — returns hourly forecast with q10/q50/q90.
- Re-runs hourly when new ECCC AQHI observation lands. Cached in SQLite.

## 3.3 Model cards (mandatory)

Every model gets a `docs/model-cards/wildfire_risk_v1.md` and `aq_forecaster_v1.md` with:
- Intended use + out-of-scope use.
- Training data: range, source, sample sizes.
- Held-out test results with confidence intervals (bootstrap 1000).
- Calibration plot and reliability diagram.
- Feature importance (SHAP global).
- Known failure modes (e.g., human-ignition wildfires near long-weekends, smoke from Pacific NW US fires not captured by 250 km radius).
- Ethical considerations: this tool is informational, not a substitute for BC Wildfire Service or BC Emergency Health Services decisions.

## 3.4 Reproducibility

- All training scripts in `scripts/train/` accept a `--seed` flag and use `numpy.random.default_rng(seed)`.
- DVC or simple Git-tracked Make targets (`make train-risk`, `make train-aq`) — DVC is overkill, use Make.
- Capture exact dataset hashes at train time and embed them in the model artifact metadata.
- Keep training notebooks in `notebooks/` for narrative; production trainers are pure scripts.

## 3.5 Verification

- [ ] `make train-risk` completes < 15 min on M2 / equivalent CPU.
- [ ] Wildfire risk model PR-AUC ≥ 0.55 on 2022+2023 test (FWI baseline ≈ 0.30 historically — this gives material headroom).
- [ ] AQ forecaster MAE @ T+24 ≤ 6 µg/m³ on 2022+2023 test (RAQDPS-FW baseline ≈ 9 µg/m³).
- [ ] Both ONNX exports load in `onnxruntime` and produce identical predictions to Python pickles within float32 tolerance.
- [ ] Model cards rendered, plots saved, attached as static assets in `apps/web/public/research/`.
- [ ] `/api/risk/grid?date=...` and `/api/aq/forecast?hours=48` respond in ≤ 200 ms (cached).

## 3.6 Deliverable

Two trained models, fully validated, with cards. The `Risk Grid` Cesium layer (Phase 2 Layer C) now shows real AI-derived colours. The AQ Monitor (Phase 4) has real numbers to render.

# Phase 4 — Air Quality Monitor (Feature 2)

> **Goal**: a dedicated `/air-quality` route that makes the Phase 3 AQ forecaster sing. Live AQHI dial, 48-hour forecast chart with uncertainty band, smoke event calendar (last 12 months), and Health Canada-aligned guidance for sensitive groups. Visually distinctive and emotionally accurate — bad air should *look* bad.

## 4.1 Page composition

Layout (12-col grid, breakpoints sm/md/lg/xl):

```
┌────────────────────────────────────────────────────────────┐
│ [hero] Current AQHI dial + status word + last updated     │
├────────────────────────────────────────────────────────────┤
│ [chart] 48-hour forecast (q10–q90 band + median line)     │
├──────────────────────────┬─────────────────────────────────┤
│ [pollutants] PM2.5 PM10 │ [stations] map of nearby        │
│ O3 NO2 SO2 with bars    │ AQHI stations (MapLibre inset)  │
├──────────────────────────┴─────────────────────────────────┤
│ [calendar] last 365 days, GitHub-style heatmap of AQHI    │
├────────────────────────────────────────────────────────────┤
│ [guidance] health guidance per current AQHI level          │
└────────────────────────────────────────────────────────────┘
```

## 4.2 The AQHI dial

A circular dial — but **not** the generic Apple Health ring. Specs:

- 320 px diameter on desktop, 240 px on iPad portrait.
- **Outer arc**: full 270° arc divided into AQHI 1-10+ tick marks. Background = thin `var(--color-stroke)` arc.
- **Filled arc**: animated from 0 to current value, colour from `--aq-1` … `--aq-plus`. Uses `stroke-dasharray` animation, 1.4 s ease-out-expo.
- **Centre value**: AQHI integer in JetBrains Mono 96 px, with a thin amber/cyan glow shadow (`--glow-ember` if AQHI ≥ 7, `--glow-cyan` otherwise).
- **Status word** below the value: "Low Risk", "Moderate", "High", "Very High" — in the display font, 24 px.
- **Pulse**: when a fresh reading arrives, the entire dial subtle-pulses (`scale: 1 → 1.02 → 1`, 600 ms). Tells the user "this is live data".

## 4.3 Forecast chart

Built with **Visx** (`@visx/xychart`, custom layers):

- X-axis: T-now → T+48h, ticks every 6 h, time formatted in Kamloops local time.
- Y-axis (primary): PM2.5 µg/m³.
- Y-axis (secondary, right): AQHI scale 1-10+.
- **Layer 1**: q10–q90 band as a soft area fill, gradient from `--aq-3` (low) to `--aq-7` (high) by Y value. Opacity 0.35.
- **Layer 2**: q50 line, 2 px, glow filter, colour mapped to AQHI band.
- **Layer 3**: observed points (last 12 hours) as 4 px circles in `--color-text-hi`.
- **Layer 4**: vertical "now" line — dashed, `--color-cyan-glow`.
- **Layer 5**: horizontal bands for AQHI categories with subtle shading, labels at right edge.
- Hover crosshair shows: time, predicted PM2.5 (with uncertainty range), implied AQHI, dominant contributor (e.g., "wildfire smoke from McDougall Creek fire, 64 km NW").

## 4.4 Pollutant breakdown panel

- Five horizontal bars (PM2.5, PM10, O3, NO2, SO2). Each bar:
  - Background bar = stroke colour.
  - Filled bar = animated to current concentration normalised vs. Canadian Ambient Air Quality Standards.
  - Numeric value in JetBrains Mono right-aligned.
  - 1-line "trend" sparkline next to it (Visx `LineSparkline`) showing last 24 h.
- Source: WAQI (which gives the component split) + ECCC AQHI for the headline.

## 4.5 Stations inset map

- **MapLibre GL** (not Cesium — keep this lightweight and 2D).
- Style: a custom dark style with subtle topographic shading (use MapLibre's `dem` source from `terrain-rgb` tiles served free by MapTiler free tier — register one key for this).
- AQHI station markers: filled circles colour-coded by current AQHI value, sized by reliability (full-size for ECCC official, 75% for WAQI crowd-sourced).
- On click: marker expands to a tooltip with station name, latest reading, last update.

## 4.6 Smoke event calendar

A 53-week × 7-day grid (one cell per day, last 365 days) styled like a GitHub contribution graph but with the AQHI palette:

- Each cell coloured by **max** AQHI that day (median for ties).
- Hover tooltip: date, max AQHI, dominant cause ("smoke from BC fires", "smoke from WA fires", "no fire — particulates from local sources", "clean").
- Click a cell → modal with that day's hourly chart and a tiny Cesium snapshot showing fires active that day (rendered as offscreen Cesium scene, exported to PNG and served from `/api/screenshots/YYYY-MM-DD`).
- The "dominant cause" attribution comes from a small heuristic: if PM2.5 was ≥ 25 µg/m³ AND any FIRMS hotspot in BC within 250 km, label "BC fire smoke"; if hotspot only in WA/OR/ID, "US Pacific NW smoke"; else "local sources / unknown".

## 4.7 Health guidance

Pulled from a static JSON file `data/geo/health_guidance.json` keyed by AQHI level, with three audiences: General, At-Risk (heart/lung disease, pregnant, children, elderly), Outdoor Workers. Mirror the wording used by Interior Health and HealthLink BC. Each block links to the canonical Interior Health page so we stay authoritative.

## 4.8 Subscriptions (no PII!)

A small "Notify me" widget. Because of the no-account constraint:
- Browser push via the Web Notifications API. The "subscription" lives in localStorage as `{ thresholdAqhi: 7, lastNotifiedAt: ISO }`.
- A simple `setInterval` on the page polls `/api/aq/current` every 5 min (when tab is visible). When AQHI ≥ threshold and ≥ 60 min since last notification, fires `Notification`.
- No backend involvement, no FCM, no cost, no PII. Documented limitation: notifications only fire while a tab is open. Acceptable for a research demo.

## 4.9 Accessibility

- The dial reads its value via `aria-label="Current AQHI: 5, moderate risk, last updated 14:32"`.
- Forecast chart has a "View as table" toggle that mounts an HTML table beneath it with the same data.
- Health guidance text uses ≥ 16 px body, ≥ 4.5:1 contrast.

## 4.10 Verification

- [ ] `/air-quality` cold loads in ≤ 2 s on broadband.
- [ ] Live AQHI updates every minute when fresh data is available.
- [ ] Forecast chart renders with both quantile band and median line; switching to "table view" shows identical data.
- [ ] Calendar shows ≥ 12 months of historical AQHI density.
- [ ] iPad layout: dial + chart stack vertically without overflow; hover behaviours map to long-press.
- [ ] Lighthouse Performance ≥ 90 (this page is mostly DOM + SVG, easy to optimise).

## 4.11 Deliverable

A page someone genuinely uses on smoke days — the kind of page where you check it, then check it again 20 minutes later because the dial is rendering uncertainty honestly. The Phase 3 AQ model finally has its rightful presentation.

# Phase 5 — Community Preparedness Hub (Feature 3)

> **Goal**: a personal, neighbourhood-aware preparedness experience at `/preparedness` that uses **only localStorage** for state. No accounts, no PII, no backend writes. The UX must feel as personal as if it remembered you, while leaking nothing.

## 5.1 Onboarding (one-time, ~30 s)

A 3-step inline wizard, not a modal. Steps:

1. **Pick your neighbourhood**. A typeahead populated from `data/geo/kamloops_neighbourhoods.geojson`. As the user types, the matching polygon highlights on a small inset Cesium camera fly-to. (Reuse the singleton globe; this just animates the camera.)
2. **Tell us your situation** (multi-select chips, all optional, none required to proceed):
   - "I have a house with a yard"
   - "I rent / live in an apartment"
   - "I have pets / livestock"
   - "I'm in a sensitive group" (heart/lung, pregnancy, elderly, children)
   - "I work outdoors"
   - "I have mobility considerations"
3. **Notification preferences**: an AQHI threshold slider (4–10) and an evacuation-alerts toggle. Both backed by Web Notifications.

Wizard answers persist as:
```ts
type PrepProfile = {
  neighbourhood: string;
  situation: string[];
  notify: { aqhiThreshold: number; evacAlerts: boolean };
  createdAt: string;
};
```

Stored in localStorage under `wildfireiq.profile.v1`. There is **no** server call. The entire profile is a UI affordance.

## 5.2 The hub layout

Three columns on desktop (12-col grid, becomes single column on iPad portrait):

- **Left (4 cols)**: live status — current evac status for *your* polygon, current AQHI for nearest station, current FWI rating, days since last meaningful rain.
- **Centre (5 cols)**: the FireSmart checklist (the centrepiece).
- **Right (3 cols)**: progress + achievements + countdown to fire season peak.

## 5.3 Personalised FireSmart checklist

The checklist is composed dynamically by combining:

1. **Base FireSmart Canada Home Ignition Zone (HIZ) actions** — the canonical 30-item list across Zones 1A (0-1.5m), 1B (1.5-10m), 2 (10-30m), 3 (30-100m). Stored in `data/firesmart/firesmart_actions.json` as:
   ```json
   {
     "id": "z1a_remove_combustibles_under_deck",
     "zone": "1A",
     "title": "Clear all combustibles from under decks",
     "category": "structural",
     "estimatedMinutes": 30,
     "cost": "free",
     "applies": { "housing": ["house"], "season": "any" }
   }
   ```
2. **Filter by user's situation** — apartment dwellers don't see "clear gutters"; pet owners get an extra block on pet evacuation kits.
3. **Sequence by season**: in May, prioritise vegetation clearing; in late August, prioritise go-bag readiness; year-round, the Emergency Plan.
4. **Group into 4 sections**: "Immediate Zone (0-1.5m)", "Intermediate Zone (1.5-30m)", "Extended Zone (30-100m)", "Plan & Go Bag".

Each item is a card:
- Title, 1-line description, est. minutes, "Why this matters" expandable.
- Photo: BC FireSmart official photos where licensing allows; otherwise iconographic illustrations we author.
- Action: checkbox + "Add photo" optional (photo stored as a base64 string in IndexedDB, never leaves the device).
- Bottom-right: point value (e.g., 50 pts for a structural action, 15 pts for an awareness one).

## 5.4 Points + achievements (gamification, local-only)

State shape:
```ts
type ProgressV1 = {
  completedActions: { id: string; completedAt: string; photo?: string }[];
  points: number;
  achievements: string[];   // achievement ids
  streakDays: number;
  lastVisitDay: string;
};
```

Stored in IndexedDB (because of photo blobs) under DB `wildfireiq.progress.v1`.

### Achievements (≥ 12, examples)
- **First Steps** — complete any 1 action.
- **Zone 1 Hero** — all Zone 1A + 1B done.
- **Photo Documentarian** — attach photos to 5 actions.
- **Smoke Aware** — review the AQ guidance page during an AQHI ≥ 7 day.
- **Neighbour** — share progress link (a generated read-only URL with profile encoded in URL hash, opt-in).
- **Streak: 7** — visit the app 7 days in a row.
- **Storm Ready** — Plan & Go Bag complete by July 1.

Each achievement is a card with custom illustrated badge. Animations on unlock: 800 ms confetti-but-tasteful effect (Motion + canvas) that respects reduced motion.

## 5.5 Live evacuation widget

For the user's neighbourhood polygon:
- Compute polygon-vs-evac-zone intersection in the browser (Turf.js `booleanIntersects`) using `/api/evac/active` data.
- Render one of three states:
  - **Clear** — calm, sage `--risk-low` accent, "No evacuation orders or alerts in your area."
  - **Alert** — amber `--risk-moderate`, "Evacuation Alert active. Be ready to leave on short notice." Includes link, issuing authority, issued time.
  - **Order** — full red `--risk-extreme` panel, pulses subtly, list of nearest reception centres.
- The widget polls `/api/evac/active` every 60 s.
- If state changes from Clear→Alert→Order, fires a Web Notification (subject to user preference).

## 5.6 Countdown + season context

- "Fire season peak: 47 days" — based on the historical Thompson-Okanagan peak of mid-August (compute from Phase 1 data, not hardcoded).
- "Days since last 5mm+ rain in Kamloops: 18" — from weather feed.
- Subtle ticker, monospace, sits in the right column.

## 5.7 Sharing (optional, opt-in)

A "Share my progress" button generates a read-only URL like `/preparedness/shared#<base64-encoded-profile-and-progress>`. Encoded entirely in the URL hash (never sent to server). Recipients see a stripped-down view with the user's progress visualised. **No personal data ever leaves the device unless the user explicitly clicks share + sends the link.**

## 5.8 Backend support for this phase

`/api/firesmart/checklist?neighbourhood=Aberdeen&situation=house,pets,sensitive&season=spring` → server returns the filtered, ordered checklist. The server is stateless: it merely composes the static JSON with the query params. **No user data is logged.**

`/api/evac/check?lat=...&lon=...` → returns `{ status: 'clear'|'alert'|'order', zone?: { ... } }`. Used by the live widget.

## 5.9 Verification

- [ ] Onboarding wizard completes in < 60 s; localStorage shows the profile.
- [ ] Killing the browser and returning → profile restored.
- [ ] Clearing site data → wizard restarts cleanly.
- [ ] Network tab shows zero outbound requests during onboarding (server is consulted only after the user clicks something that needs it, like "view evac details").
- [ ] Achievements fire on completion thresholds; confetti respects reduced motion.
- [ ] Photo uploads stored entirely in IndexedDB; verify via DevTools that no XHR/fetch sends the photo.
- [ ] Sharing link is fully self-contained; opening it in incognito reproduces the shared view.
- [ ] iPad: checklist scrolls smoothly, photo capture button uses `<input type="file" capture="environment">` for native camera.

## 5.10 Deliverable

A surprisingly intimate experience for an app that knows nothing about you. People keep coming back because the achievements pull them in, the checklist meets them where they are, and the evacuation widget might one day actually save their life.

# Phase 6 — Climate Trend Module (Feature 4)

> **Goal**: a single page at `/climate` that tells the *story* of how the Thompson-Okanagan's fire seasons and climate have changed — and projects forward to 2050 — using ClimateData.ca CMIP6 data and the historical fire corpus from Phase 1. This is the "why this all matters" page.

## 6.1 Data inputs (already ingested in Phase 1)

- `data/processed/fires_unified.parquet` — historical fire records 1999–today (extend to 1950 if data allows).
- `data/processed/weather_kamloops_daily.parquet` — daily Kamloops weather since ~1995.
- `data/raw/climatedata_projections/{ssp126,ssp245,ssp585}.csv` — CMIP6 ensemble projections to 2100.
- A precomputed `data/processed/seasonal_metrics.parquet` joining the above into per-year metrics:
  - Total area burned (ha) in BBOX
  - Number of fires (size ≥ 1 ha)
  - Largest single fire (ha)
  - Fire-season length (first to last ignition)
  - Mean July temperature (Kamloops A)
  - Mean July-August precipitation total
  - Mean July-August VPD
  - Mean July-August max FWI
  - Days with FWI ≥ 19 (extreme threshold)

## 6.2 Page narrative (scrollytelling)

The page is **scrollytelling** — as the user scrolls, the central viz transforms. Built using a sticky pinned section + IntersectionObserver scroll triggers (no library — just custom hooks + GSAP ScrollTrigger).

### Section 1 — "Three decades of fire"
Hero: full-width Visx area chart of annual area burned, 1995 → today. Bars in `--color-ember-500` glow; a horizontal mean line (1995-2010 baseline) drawn dashed.
Annotations float in (Motion staggered) for landmark seasons: 2003 (Okanagan Mountain Park), 2017 (Elephant Hill), 2018, 2021 (Lytton), 2023 (record Canadian season).

### Section 2 — "Hotter, drier, longer"
Three stacked sparkline panels for July temperature, July-Aug precipitation, July-Aug VPD. Each shows the timeseries with a fitted trend line + slope label ("+1.6°C since 1995"). Trend computed via Theil-Sen estimator (robust to outliers) — show CIs from bootstrap.

### Section 3 — "Fire season starts earlier and ends later"
A "fire season ribbon" diagram — for each year, a horizontal bar from first ignition DOY to last ignition DOY, with colour intensity = total burned area. Visually obvious lengthening over time.

### Section 4 — "What's coming"
Switch to projection mode. The same temperature panel from Section 2 now extends to 2050 with three SSP scenarios:
- SSP1-2.6 — low emissions, soft `--aq-3` line
- SSP2-4.5 — middle, `--risk-moderate` line
- SSP5-8.5 — high, `--risk-extreme` line
Ensemble spread shown as shaded bands per scenario. User can toggle each scenario via segmented control.

### Section 5 — "What this means for fire weather"
A simple compute-on-the-fly heuristic: project the historical FWI ~ f(temp, precip) relationship onto SSP2-4.5 / SSP5-8.5 climate to estimate **future days with FWI ≥ 19** by decade. (We disclose this is a coarse extrapolation, not a full model run.) Bar chart by decade: 2000s, 2010s, 2020s, 2030s, 2040s.

### Section 6 — "TRU campus carbon (optional)"
Conditional section. Renders only if `data/tru_carbon.csv` exists. If institutional data becomes available (per proposal), this shows TRU's annual carbon emissions trend with a TRU-Sustainability-Office target line. Feature-flag via env var `VITE_ENABLE_TRU_CARBON=true`.

## 6.3 Visual treatments

- All charts in **Visx**, custom-styled to match the design tokens.
- A subtle "data-paper" treatment on the page background: a low-contrast topographic line pattern (SVG, generated once from a Cesium World Terrain elevation crop of the Thompson-Okanagan) sits behind the content at 4% opacity. Earns the academic gravitas without being twee.
- Annotations are sticky-noted into the chart area, not floating randomly.

## 6.4 Methodology footer + downloads

Every chart has an info `(i)` icon revealing:
- Source (link to ClimateData.ca / ECCC / DataBC).
- Method (e.g., "Theil-Sen slope, 10,000 bootstraps").
- "Download CSV" button — pulls from `/api/climate/...` with `Accept: text/csv`.

## 6.5 Verification

- [ ] All six sections render with real data; the sticky scroll transitions are smooth on iPad.
- [ ] Each chart's "Download CSV" produces a valid CSV opened by Excel/Numbers.
- [ ] Trend slopes are within published Pacific Climate Impacts Consortium (PCIC) ranges for the Thompson-Okanagan — sanity check against PCIC's regional reports.
- [ ] When `VITE_ENABLE_TRU_CARBON=false`, Section 6 is fully hidden (not just empty).
- [ ] Scrollytelling on iPad portrait works without the sticky element jittering.
- [ ] Print stylesheet generates a clean 4-page PDF of the page (the app's "research artifact" output).

## 6.6 Deliverable

A page that an academic, a journalist, or a local councilor could each cite. Strong narrative, beautifully presented, methodologically transparent.

# Phase 7 — Polish, Performance, iPad/Desktop Optimization, Demo

> **Goal**: take a working app and turn it into something that looks and runs like a multi-million-dollar product. This phase is the difference between "an impressive student project" and "did Anthropic build this?". Two sittings, ruthlessly focused on the last 5% that's worth 50% of the perception.

## 7.1 Performance pass

### Frontend
- **Bundle audit**: run `pnpm build && pnpm dlx vite-bundle-visualizer`. Anything over 200 KB gzipped that isn't Cesium gets investigated. Cesium itself is ~ 4 MB gz — accept and lazy-load.
- **Code-split routes**: `React.lazy` + `Suspense` for `/air-quality`, `/preparedness`, `/climate`. The globe stays eager (it's the heaviest but it's the front door).
- **Cesium tree-shaking**: confirm only imported modules are bundled. Use the official `@cesium/engine` + `@cesium/widgets` packages, not the kitchen-sink `cesium` umbrella, where possible.
- **Image pipeline**: every PNG run through `oxipng -o 4`; every photo through `cwebp -q 80`. Author SVGs preferred for icons (already iconic, infinitely scalable).
- **Font subsetting**: subset display fonts to Latin-only with `glyphhanger`. Cuts ~70% off font payloads.
- **`requestIdleCallback`** for prefetching `/api/risk/grid` + `/api/aq/forecast` on the globe page so navigating to AQ feels instant.
- **Service Worker** (Workbox): cache the app shell, fonts, Cesium static assets, and recent `/api/*` GETs with stale-while-revalidate. Page works offline (with stale data).

### Backend
- **Response caching**: `cache-control: public, max-age=60` on most GETs; `s-maxage=300` for historical endpoints.
- **DuckDB warm-up**: on FastAPI startup, pre-open DuckDB and run a tiny no-op query. First-request latency drops from ~400 ms to ~20 ms.
- **HTTP/2** via Caddy or h2 in uvicorn so multiple Cesium tile requests pipeline.
- **gzip + brotli** on responses where supported.

### Targets (must hit before moving on)
- Cold load to interactive (globe page) ≤ 3.0 s on broadband, ≤ 6.0 s on simulated 4G.
- 60 fps locked on M1+ desktops with all default layers.
- 50+ fps on iPad Pro M2 Safari.
- Lighthouse Performance ≥ 80 (globe), ≥ 90 (every other page).
- Lighthouse Accessibility ≥ 95 across the app.
- Total JS payload (gz, excluding Cesium) ≤ 220 KB.

## 7.2 iPad polish

- All hover states have a long-press equivalent.
- Pointer events properly handled (`pointer-events-fine` vs `pointer-events-coarse` Tailwind variants).
- Touch targets ≥ 44 px everywhere except Cesium's own controls.
- Pinch-zoom on charts disabled in favour of in-app zoom controls (prevents browser-level zoom fighting with Visx behaviours).
- Status bar overlap on Safari handled with `viewport-fit=cover` + `env(safe-area-inset-*)` paddings on the AppShell.
- Test on iPad Pro 12.9" + iPad Mini + iPad Air sizes via Safari Tech Preview's responsive design mode.

## 7.3 Visual final pass

Walk every screen with the frontend-design skill checklist:
- [ ] No Inter, Roboto, Arial visible anywhere (audit DevTools computed styles).
- [ ] No purple-on-white gradient anywhere.
- [ ] Every screen has at least one moment of distinctive detail (a glow, a grain texture, a bespoke illustration, a non-obvious motion).
- [ ] Numerals rendered exclusively in JetBrains Mono.
- [ ] Animations consistent in feel — same easing tokens used app-wide.
- [ ] All CTAs use the ember spectrum; cool accents reserved strictly for live-data signals.
- [ ] Loading states are interesting (a slow shimmer on a spinner is a lost moment — replace with Cesium-themed loaders).
- [ ] Empty states (no fires today!) have copy with personality, not "No data."

## 7.4 Copy + voice pass

- A single editor (you) reads every string. Tone: precise, calm, slightly cinematic. Never "Oops! Something went wrong." Always specific.
- Numbers always have units. Times always have timezones. Areas always in hectares (with km² in tooltip).
- Citations on every chart. Attribution panel reachable from the AppShell footer.

## 7.5 Documentation

- `README.md`: 60-second pitch, screenshots, run instructions, architecture diagram, attribution.
- `docs/data-dictionary.md`: every field of every parquet file documented.
- `docs/model-cards/*.md`: from Phase 3, polished.
- `docs/api-keys-setup.md`: how to obtain Cesium Ion, FIRMS, WAQI tokens (with screenshots).
- `docs/architecture.md`: the diagram from this plan plus a request lifecycle for one feature end-to-end.
- A `CITATION.cff` file so others can cite the work.

## 7.6 Testing

- **Backend**: pytest coverage ≥ 80% on routers, ingest parsers, and ML inference adapters.
- **Frontend**: Vitest unit tests for hooks + utility functions (≥ 70% on `src/lib/`). Playwright smoke tests: globe loads, AQ page loads, prep wizard completes, climate page scrolls.
- **Data**: a `tests/data_quality/` set asserting things like "every fire row has valid coordinates within Canada" and "no AQHI reading > 12".

## 7.7 Demo recording

Record a **90-second** screen capture (1440×900) that you'll attach to the TRU final report and use on social/portfolio:

1. **0–8s** — splash → globe fly-in over Thompson-Okanagan.
2. **8–22s** — toggle layers; click a fire; show side panel + camera preset to it.
3. **22–35s** — switch to AQ Monitor; let dial pulse; scrub forecast chart.
4. **35–55s** — Preparedness Hub: complete a checklist item, unlock an achievement, show evac widget.
5. **55–78s** — Climate page: scrollytelling sweep through 30 yrs to projections.
6. **78–90s** — return to globe; fade to logo + URL + attribution.

Exported as MP4 (H.264, 30 fps, ~ 8 Mbps) and WebM (VP9). Hosted in `apps/web/public/demo/` so the README plays it inline.

## 7.8 Open-source release prep

- License: **MIT** for code, **CC-BY-4.0** for written content.
- A `THIRD_PARTY_NOTICES.md` listing every dependency's license.
- A `CONTRIBUTING.md` (even though contributions aren't expected during the grant — it's standard).
- Public GitHub repo with topics: `wildfire`, `climate`, `british-columbia`, `cesiumjs`, `fastapi`, `geospatial`, `ml`.
- Pinned issue: "What's next" — a roadmap for post-grant work (Indigenous Knowledge integration, Vancouver Island, FN-led fire data partnerships).

## 7.9 Final verification (definition of done)

- [ ] All Phase 0-7 verifications green.
- [ ] Demo MP4 recorded and embedded in README.
- [ ] Tag `v1.0.0` on the repo.
- [ ] One full end-to-end manual test: cold load → globe → click fire → AQ page → Prep wizard → Climate page. **Every transition feels intentional. Nothing jitters. Nothing surprises.**
- [ ] You'd happily put the URL on the homepage of your portfolio.

## 7.10 Deliverable

The platform the proposal promised, plus the polish neither the grant board nor your future self imagined. **Ship it.**

# Appendix A — Environment variables (`.env.example`)

```bash
# Required
CESIUM_ION_TOKEN=eyJhbGciOiJIUzI1NiJ9...               # https://ion.cesium.com
FIRMS_MAP_KEY=00000000000000000000000000000000        # https://firms.modaps.eosdis.nasa.gov/api/map_key
WAQI_TOKEN=0000000000000000000000000000000000000000   # https://aqicn.org/data-platform/token

# App
VITE_API_BASE_URL=http://localhost:8000
DATABASE_URL=sqlite+aiosqlite:///./data/wildfireiq.db
DUCKDB_PATH=./data/analytics.duckdb

# Feature flags
VITE_ENABLE_TRU_CARBON=false
VITE_ENABLE_NDVI_LAYER=false

# Optional (Phase 2 stretch)
GEE_SERVICE_ACCOUNT_JSON=                              # Earth Engine service account JSON, base64
MAPTILER_KEY=                                          # Optional, for the AQ Monitor inset map
```

# Appendix B — Required external account signups

| Service | Purpose | Sign-up URL | Free quota | Phase needed |
|---|---|---|---|---|
| **Cesium Ion** | World Terrain, OSM Buildings, Bing imagery | https://ion.cesium.com/signin/ | 5 GB storage, **15 GB streaming/month** | Phase 0 |
| **NASA FIRMS** | Satellite hotspot API | https://firms.modaps.eosdis.nasa.gov/api/map_key | 5,000 transactions / 10 min | Phase 1 |
| **WAQI/AQICN** | Air-quality cross-check + pollutant split | https://aqicn.org/data-platform/token | ~1,000 req/sec practical | Phase 1 |
| **MapTiler Cloud** *(optional)* | Terrain-RGB tiles for AQ inset map | https://www.maptiler.com/cloud/ | 100,000 tile req / month | Phase 4 |
| **Google Earth Engine** *(optional, stretch)* | NDVI vegetation health layer | https://earthengine.google.com/signup/ | Generous non-commercial | Phase 2 stretch |

Three signups before Phase 0 verification: **Cesium Ion, FIRMS, WAQI**.

# Appendix C — Final repo file tree (target end-of-Phase-7)

```
WildFire-IQ/
├── apps/
│   ├── web/
│   │   ├── public/
│   │   │   ├── cesium/                       # Cesium static (auto-copied)
│   │   │   ├── fonts/                        # self-hosted PP Neue Machina / Bricolage / Geist / JetBrains Mono
│   │   │   ├── textures/grain.png
│   │   │   ├── icons/                        # SVG layer icons
│   │   │   ├── photos/firesmart/             # licensed FireSmart photos
│   │   │   ├── research/                     # model card plots
│   │   │   └── demo/                         # mp4/webm demo
│   │   ├── src/
│   │   │   ├── app.tsx                       # router + providers
│   │   │   ├── app.css                       # tailwind + tokens
│   │   │   ├── shell/                        # AppShell, left rail, top bar
│   │   │   ├── features/
│   │   │   │   ├── globe/                    # Cesium viewer, layers, panels
│   │   │   │   ├── air-quality/
│   │   │   │   ├── preparedness/
│   │   │   │   └── climate/
│   │   │   ├── lib/
│   │   │   │   ├── api/                      # TanStack Query hooks per endpoint
│   │   │   │   ├── cesium-helpers/
│   │   │   │   ├── motion-presets.ts
│   │   │   │   └── h3.ts
│   │   │   ├── stores/                       # Zustand stores
│   │   │   └── types/                        # imports from @wildfireiq/shared-types
│   │   ├── vite.config.ts
│   │   └── package.json
│   └── api/
│       ├── wildfireiq_api/
│       │   ├── main.py
│       │   ├── settings.py
│       │   ├── db.py
│       │   ├── duckdb_pool.py
│       │   ├── scheduler.py
│       │   ├── ingest/
│       │   │   ├── base.py
│       │   │   ├── databc_fires_current.py
│       │   │   ├── firms_hotspots.py
│       │   │   ├── databc_fires_historical.py
│       │   │   ├── open_meteo.py
│       │   │   ├── eccc_climate.py
│       │   │   ├── cwfis_fwi.py
│       │   │   ├── geomet_aqhi.py
│       │   │   ├── waqi.py
│       │   │   ├── firework_smoke.py
│       │   │   ├── bcem_evac.py
│       │   │   └── climatedata_projections.py
│       │   ├── etl/build_features.py
│       │   ├── ml/
│       │   │   ├── risk/{train.py, infer.py}
│       │   │   └── aq/{train.py, infer.py}
│       │   └── routers/
│       │       ├── fires.py  risk.py  aq.py  weather.py
│       │       ├── fwi.py    evac.py  climate.py  firesmart.py
│       │       └── screenshots.py
│       ├── tests/
│       └── pyproject.toml
├── packages/
│   ├── shared-types/api.d.ts
│   └── design-tokens/{tokens.css, fonts.css, tailwind-preset.ts}
├── data/
│   ├── geo/{thompson_okanagan.geojson, kamloops_city.geojson, kamloops_neighbourhoods.geojson, fire_centres.geojson, health_guidance.json}
│   ├── firesmart/firesmart_actions.json
│   ├── raw/...
│   ├── processed/...
│   ├── models/...
│   └── logs/
├── notebooks/{eda_fires.ipynb, eda_aq.ipynb, model_dev_risk.ipynb, model_dev_aq.ipynb}
├── scripts/
│   ├── ingest/bootstrap.py
│   └── train/{train_risk.py, train_aq.py}
├── docs/
│   ├── architecture.md
│   ├── data-dictionary.md
│   ├── api-keys-setup.md
│   └── model-cards/{wildfire_risk_v1.md, aq_forecaster_v1.md}
├── .env.example
├── .gitignore
├── pnpm-workspace.yaml
├── package.json
├── pyproject.toml
├── README.md
├── LICENSE
├── CITATION.cff
└── implementationplan.markdown    ← this file
```

# Appendix D — Design tokens cheat-sheet (for AI agents in later phases)

When in doubt, reach for these:

| Use case | Token |
|---|---|
| Page background | `bg-[--color-bg-0]` |
| Card surface | `bg-[--color-bg-1]` with `border border-[--color-stroke]` |
| Hover surface | `hover:bg-[--color-bg-3]` |
| Primary CTA | `bg-[--color-ember-500] text-white` + `--glow-ember` on hover |
| Live data accent | `text-[--color-cyan-glow]` — **only** for live-data signals, never decorative |
| Heading | `font-display text-[--color-text-hi]` |
| Body | `font-sans text-[--color-text-hi]` |
| Numerals/data | `font-mono` with `tabular-nums` |
| Risk colours (semantic) | `--risk-low`, `--risk-moderate`, `--risk-high`, `--risk-extreme` |
| AQHI colours | `--aq-1` through `--aq-plus` |
| Standard transition | `transition duration-[var(--dur-base)] ease-[var(--ease-out-expo)]` |
| Cinematic transition | `duration-[var(--dur-cinema)] ease-[var(--ease-in-out-quart)]` |

Rules:
1. **No purple gradient on white**. Ever.
2. **No Inter, Roboto, Arial**. Ever.
3. **JetBrains Mono for every visible number** (temperatures, AQI, hectares, coordinates, timestamps).
4. **Cyan is sacred** — reserve for live-data pulses only.
5. **One bold accent per screen**. The ember palette dominates; the cool side is whisper.

# Appendix E — Phase invocation guide (for the human operator)

When a phase is ready to run, simply tell Claude Code:

> `go phase 0` — and the agent reads this plan, executes Phase 0 end-to-end, runs the verification checklist, and reports back.

Recommended pattern per phase:

1. **Plan-mode read**: agent re-reads this file's relevant phase section.
2. **Subagent fan-out**: complex phases (1, 2, 3) should fan out to parallel subagents — one per major task.
3. **Verification step**: agent runs the verification checklist and reports green/red. Reds halt and ask for direction.
4. **Phase commit**: a single git commit per phase tagged `phase-N-complete`.
5. **Demo screenshot**: agent saves a screenshot to `docs/progress/phase-N.png` so you can see momentum visually.

# Appendix F — Risk register & open questions

| Risk | Likelihood | Mitigation |
|---|---|---|
| Cesium Ion 15 GB/month exceeded during dev | Medium | Tile cache via Service Worker; Sentinel-2 EOX as primary imagery; switch to Bing/Ion only when zoomed in |
| BC Emergency ArcGIS endpoint changes between fire seasons | High | Endpoint discovery wrapped in a config probe at app start; RSS fallback; graceful degraded UI |
| Open-Meteo non-commercial tier insufficient | Low | < 100 req/day in actual use; cache aggressively |
| FIRMS Canada polygon endpoint timeouts | Confirmed | Use BBOX endpoint (already specified) |
| Wildfire risk model PR-AUC < 0.55 | Medium | Iterate on features (lightning, NDVI); revise thresholds; document honestly in model card — research outcomes don't have to be triumphant to be valid |
| iPad performance below 50 fps with all layers | Medium | Tier layer detail by zoom + device class; auto-disable wind particles + smoke WMS on `coarse` pointer devices |
| Google Photorealistic 3D Tiles tempt us in but don't cover Kamloops | Confirmed | Plan already uses Cesium World Terrain + OSM Buildings; do not change |
| Open question — Indigenous Knowledge integration | Open | Defer to post-grant per proposal; placeholder section in `/about` ready to receive content from Wildfire Resilience Consortium of Canada partnerships |

# Appendix G — Attribution copy (for the AppShell footer)

```
Data: BC Wildfire Service · Environment & Climate Change Canada · NASA FIRMS · Open-Meteo
      · Natural Resources Canada CWFIS · BC Air Data Archive · WAQI · ClimateData.ca
      · BC Emergency Management · OpenStreetMap contributors · ESA Copernicus Sentinel-2
      · Cesium ion · Cesium OSM Buildings.

Built by Deeparsh Singh Dang at Thompson Rivers University, with the support of the
TRU Sustainability Research Grant for Students 2025-2026. Code: MIT. Content: CC-BY-4.0.

This tool is informational. It is not a substitute for guidance from the BC Wildfire
Service, BC Emergency Management, or BC Emergency Health Services. In a wildfire
emergency, follow the directions of the authorities.
```

# Appendix H — Quick-start commands (final)

```bash
# Install
pnpm install
uv sync

# One-time bootstrap (downloads 25 yrs of fires + climate)
uv run python scripts/ingest/bootstrap.py

# Train models
make train-risk train-aq

# Run dev (frontend on :5173, API on :8000)
pnpm dev

# Run tests
pnpm test && uv run pytest

# Build production bundle (locally — not deploying)
pnpm build
```

---

**End of plan. The next words you should ever say in this repo are: `go phase 0`.**
<!-- END -->
