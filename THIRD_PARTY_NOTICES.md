# Third-party notices

WildfireIQ Kamloops depends on the following open-source projects. Each is listed with its license. Full text for individual licenses is available from the linked project pages.

## Frontend (`apps/web`)

| Package | License | Use |
|---|---|---|
| React | MIT | UI framework |
| TypeScript | Apache-2.0 | Type system |
| Vite | MIT | Build + dev server |
| CesiumJS | Apache-2.0 | 3D globe |
| Resium | MIT | React bindings for Cesium |
| Tailwind CSS | MIT | Styling |
| Zustand | MIT | UI state |
| TanStack Query | MIT | Server-state caching |
| Motion (framer-motion) | MIT | Animation |
| Visx | MIT | Chart primitives |
| h3-js | Apache-2.0 | H3 hex tiling |
| React Router | MIT | Routing |
| vite-plugin-cesium | MIT | Cesium asset wiring for Vite |
| Vitest | MIT | Frontend tests |
| @testing-library/react | MIT | Component test helpers |

## Backend (`apps/api`)

| Package | License | Use |
|---|---|---|
| FastAPI | MIT | API framework |
| Uvicorn | BSD-3-Clause | ASGI server |
| Pydantic | MIT | Data validation |
| Pydantic Settings | MIT | Env-driven config |
| SQLAlchemy | MIT | DB layer |
| aiosqlite | MIT | Async SQLite |
| DuckDB | MIT | Analytics engine |
| pandas | BSD-3-Clause | Tabular processing |
| numpy | BSD-3-Clause | Numerics |
| pyarrow | Apache-2.0 | Parquet I/O |
| LightGBM | MIT | ML — both models |
| scikit-learn | BSD-3-Clause | Calibration + utilities |
| Shapely | BSD-3-Clause | Geometry for evac check |
| APScheduler | MIT | Cron-style ingest scheduling |
| structlog | MIT / Apache-2.0 | Logging |
| tenacity | Apache-2.0 | Retry logic |
| httpx | BSD-3-Clause | HTTP client |
| orjson | Apache-2.0 / MIT | Fast JSON |
| onnxmltools | Apache-2.0 | LightGBM → ONNX export |
| onnxruntime | MIT | ONNX inference |
| pytest | MIT | Backend tests |

## Data sources (every one is free)

| Source | Licence / Terms | Used for |
|---|---|---|
| BC Wildfire Service · DataBC | Open Government Licence — British Columbia | Current + historical fires |
| NASA FIRMS (USFS NRT) | Free public use, attribution required | Satellite hotspots |
| Open-Meteo | CC-BY 4.0 | Weather (live, forecast, ERA5 archive, CAMS AQ) |
| Environment and Climate Change Canada — MSC GeoMet | Open Government Licence — Canada | AQHI, smoke (RAQDPS-FW WMS) |
| World Air Quality Index (WAQI / AQICN) | Free with API token; attribution required | Pollutant readings |
| BC Emergency Management Climate Readiness (EMCR) | Open data | Evacuation orders / alerts / rescinds |
| Natural Resources Canada — CWFIS | Open public access | Fire Weather Index (when reachable) |
| ClimateData.ca | Open Government Licence — Canada | CMIP6 projections structure |
| Cesium Ion | Free tier; attribution required | World Terrain + OSM Buildings tiles |
| H3 cell density · BC fires | Derived in-project | Risk grid |

## Fonts

| Font | License | Source |
|---|---|---|
| Geist | OFL-1.1 | Vercel |
| JetBrains Mono | OFL-1.1 | JetBrains |
| Space Grotesk (display) | OFL-1.1 | Florian Karsten Typefaces |

Subset to Latin per the Phase 7 polish pass.

## Notes

This list is maintained by hand. For an automated dependency report, run `pnpm licenses ls` in `apps/web/` or `uv pip list` in `apps/api/`.
