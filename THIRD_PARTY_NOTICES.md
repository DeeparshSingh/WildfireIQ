# Third-party notices

Everything WildfireIQ depends on is listed here with its licence. The lists
mirror `apps/web/package.json` and `apps/api/pyproject.toml`; if a dependency
is added or removed there, update this file in the same change.

## Web app (`apps/web`)

| Package | Licence | Used for |
|---|---|---|
| React, React DOM | MIT | UI |
| React Router | MIT | Routing |
| TypeScript | Apache-2.0 | Types |
| Vite, @vitejs/plugin-react | MIT | Build and dev server |
| CesiumJS | Apache-2.0 | 3D globe |
| Resium | MIT | React bindings for Cesium |
| vite-plugin-cesium | MIT | Serves Cesium's static assets |
| Tailwind CSS, @tailwindcss/vite | MIT | Styling |
| Zustand | MIT | UI state |
| TanStack Query | MIT | Data fetching and caching |
| Motion | MIT | Animation |
| Visx (axis, curve, grid, group, scale, shape) | MIT | Charts |
| h3-js | Apache-2.0 | H3 hexagon boundaries for the risk grid |
| Biome | MIT OR Apache-2.0 | Lint and format |
| Vitest, jsdom, @testing-library/react | MIT | Tests |
| concurrently | MIT | Runs web and API together in `pnpm dev` |

## Backend (`apps/api`)

| Package | Licence | Used for |
|---|---|---|
| FastAPI | MIT | API framework |
| Uvicorn | BSD-3-Clause | ASGI server |
| Pydantic, pydantic-settings | MIT | Validation and configuration |
| SQLAlchemy, aiosqlite | MIT | The `ingest_runs` log in SQLite |
| httpx | BSD-3-Clause | HTTP client for every ingest job |
| tenacity | Apache-2.0 | Retries on transient upstream errors |
| APScheduler | MIT | Cron-style scheduling of ingest jobs |
| structlog | MIT OR Apache-2.0 | Structured logging |
| pandas, NumPy | BSD-3-Clause | Data processing |
| pyarrow | Apache-2.0 | Parquet read and write |
| Shapely | BSD-3-Clause | Geometry: bounding boxes, point-in-polygon evacuation check |
| h3 | Apache-2.0 | H3 hexagon indexing |
| LightGBM | MIT | Both machine-learning models |
| scikit-learn, joblib | BSD-3-Clause | Isotonic calibration, metrics, model persistence |
| pytest, pytest-asyncio, ruff | MIT / Apache-2.0 / MIT | Tests and lint (development only) |

## Fonts (self-hosted in `apps/web/public/fonts`)

| Font | Licence | Author |
|---|---|---|
| Bricolage Grotesque | SIL OFL 1.1 | Mathieu Triay |
| Geist | SIL OFL 1.1 | Vercel |
| JetBrains Mono | SIL OFL 1.1 | JetBrains |

## Data sources

Attribution is shown in the app beside the data it applies to.

| Source | Terms | Used for |
|---|---|---|
| BC Wildfire Service via DataBC | Open Government Licence – British Columbia | Current and historical fires |
| BC Emergency Management and Climate Readiness (EMCR) | Open data | Evacuation orders, alerts, rescinds |
| NASA FIRMS | Public use, attribution required | Satellite thermal hotspots (VIIRS, MODIS) |
| Environment and Climate Change Canada — MSC GeoMet | Open Government Licence – Canada | AQHI observations, FireWork smoke forecast (WMS) |
| Natural Resources Canada — CWFIS | Open public access | Fire Weather Index stations, when the service is reachable |
| Open-Meteo | CC BY 4.0 | Weather forecast, ERA5 reanalysis archive, CAMS air quality |
| World Air Quality Index (WAQI / AQICN) | Requires a token, attribution required | Pollutant breakdown for Kamloops |
| FireSmart Canada | Public guidance | The 30 checklist actions (curated) |
| Health Canada | Public guidance | AQHI health bands |
| Cesium Ion | Requires an access token, attribution required | World terrain and aerial imagery |

## Services

| Service | Used for |
|---|---|
| OpenRouter, routing to Z.ai GLM 5.3 Flash | The in-app assistant. Optional; the platform runs without it. |

This file is maintained by hand. For a generated report: `pnpm licenses ls`
in `apps/web/`, or `uv tree` in `apps/api/`.
