# WildfireIQ Kamloops

AI-powered wildfire risk, air quality, and community preparedness platform for the Thompson-Okanagan region of British Columbia.

> **Status**: Phase 0 — foundation complete. See [`implementationplan.markdown`](./implementationplan.markdown) for the full build plan.

## Quick start

```bash
# 1. Install dependencies
pnpm install
pnpm api:install

# 2. Set up environment variables
cp .env.example .env
# Then edit .env and add your Cesium Ion token (free signup at https://ion.cesium.com)

# 3. Run dev (frontend on :5173, API on :8000)
pnpm dev
```

## Required free signups

| Service | Purpose | Sign-up |
|---|---|---|
| Cesium Ion | 3D globe terrain + OSM buildings + Bing imagery | https://ion.cesium.com/signin/ |
| NASA FIRMS | Satellite hotspot data (Phase 1+) | https://firms.modaps.eosdis.nasa.gov/api/map_key |
| WAQI / AQICN | Air-quality cross-check (Phase 1+) | https://aqicn.org/data-platform/token |

All free tiers are well within our usage envelope.

## Stack

- **Frontend**: React 18 + TypeScript + Vite + Tailwind v4 + Resium (CesiumJS) + Motion + TanStack Query + Zustand
- **Backend**: FastAPI + Python 3.12 + SQLAlchemy 2 + DuckDB + APScheduler
- **ML**: scikit-learn + LightGBM + XGBoost (Phase 3)
- **Storage**: SQLite (operational) + DuckDB (analytical) + Parquet (raw)

## Repo layout

See `implementationplan.markdown` Appendix C for the full file tree and architecture.

## Funded by

TRU Sustainability Research Grant for Students 2025-2026.
Supervisor: Dr. Ghazanfar Latif, Department of Computing Science, Thompson Rivers University.

## License

Code: MIT. Content: CC-BY-4.0.

This tool is informational. It is not a substitute for guidance from the BC Wildfire Service, BC Emergency Management, or BC Emergency Health Services. In a wildfire emergency, follow the directions of the authorities.
