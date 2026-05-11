# Phase 3 — Wildfire Risk Classifier (AI Risk Grid layer live)

**Status**: ✅ Wildfire risk model trained, validated, deployed, and rendering on the globe as a colour-coded H3 hex grid.
**Date**: 2026-05-10

## What was built

### Historical-data bootstrap
| Dataset | Rows | Source |
|---|---|---|
| `fires_historical.parquet` | **15,996** BC fire incidents, 1999-2025 | DataBC `PROT_HISTORICAL_INCIDENTS_SP` via WFS pagination |
| `weather_kamloops_archive_daily.parquet` | **9,992** daily rows, 1999-today | Open-Meteo ERA5 archive at Kamloops centroid |

### Derived FWI (Van Wagner system)
- `wildfireiq_api/ml/fwi.py` — full Canadian Forest Fire Weather Index port: FFMC, DMC, DC, ISI, BUI, FWI, DSR.
- Implemented from Van Wagner & Pickett (1985), with seasonal reset (winter months → spring start values) and day-length factors tuned for ~50°N.
- **Permanently replaces** the dependency on NRCan's CWFIS GeoServer (which has been HTTP-502'd for the entire build window).

### Feature engineering (`wildfireiq_api/ml/features.py`)
40 features per day:
- Current-day weather (8): temp max/min, RH min, wind max + gust, precip, VPD, ET₀
- FWI codes (7): FFMC / DMC / DC / ISI / BUI / FWI / DSR
- Lagged + rolled (20): 1-day lag, 7-day lag, 7-day mean, 30-day mean for {temp, RH, wind, precip, VPD}
- Drought (3): `precip_sum7`, `precip_sum30`, `dry_spell_days`
- Calendar (2): `doy_sin`, `doy_cos`, `month`

Output: `features_risk_daily.parquet` (9,992 daily rows, 45 columns, 33% fire-day base rate) + `cell_density.parquet` (185 H3 r=5 hex cells across Thompson-Okanagan, with per-cell historical fire counts).

### Trained model (`wildfireiq_api/ml/train_risk.py`)
- **LightGBM binary classifier**, 63 leaves, lr 0.04, lambda-l2 1.0, isotonic calibration.
- Train 1999-2021 (8,394 days) → Val 2022 (365) → Test 2023 (365).
- Saved as `data/models/wildfire_risk_v1/{model.txt, calibrator.joblib, metrics.json, features.json}`.

| Held-out 2023 test | Our model | FWI baseline | Climatology |
|---|---|---|---|
| **PR-AUC** | **0.663** | 0.515 | 0.290 |
| **ROC-AUC** | **0.870** | — | — |
| **Brier** | **0.136** | — | — |

**+14.8 PR-AUC points over FWI-threshold** and **2.3× over climatology** — solid generalisation on a held-out year that was atypically severe.

### Inference (`wildfireiq_api/ml/risk_infer.py`)
- Loads model + calibrator + density once via `lru_cache`.
- Each `predict_grid()` call:
  1. Re-runs Van Wagner on the full weather archive (chronological so carryover is correct).
  2. Predicts P(fire-day) from yesterday's features → calibrates → bucketed risk classes.
  3. Multiplies by each cell's sqrt-normalised historical weight → per-cell risk score.

### API
- `GET /api/risk/grid` → full 185-cell grid + region probability + observation day.
- `GET /api/risk/today?cell=<h3>` → single cell detail.

### Frontend
- **`RiskGridLayer.tsx`** — new Cesium layer that fetches `/api/risk/grid` and renders 185 H3 r=5 hexagonal polygons coloured by risk class (Low/Moderate/High/Extreme).
  - Uses `h3-js/cellToBoundary` for exact hex geometry.
  - Each hex has a separate clamped polyline outline.
  - Click → side panel with full feature info.
- **`useRiskGrid()`** TanStack Query hook, 30-min refetch interval (grid only changes daily).
- **LayerToggleBar** — "AI Risk Grid" added as the 6th layer, default OFF. Badge counts the High+Extreme cells (the "actionable" subset).
- **LayerDetailModal `<RiskBrowser>`** — search + class filter chips (Extreme/High/Moderate/Low), each cell clickable → cinematic flyTo to its centroid.
- **FeatureInfoPanel `<RiskDetail>`** — colour-glowing risk class header, P(cell) and P(region) percentages, historical fire count, model attribution footer.

### Model card (`docs/model-cards/wildfire_risk_v1.md`)
Full Anthropic-style model card: intended use, training data, splits, metrics, baselines, top features, calibration, known limitations, reproducibility, ethical considerations.

## Verification

| Check | Result |
|---|---|
| Historical bootstrap | ✅ 15,996 fires + 9,992 daily weather rows |
| Van Wagner FWI computed correctly | ✅ 9,992 / 9,992 days have full FWI codes |
| Feature pipeline | ✅ 45-column features Parquet, 185 cells in density grid |
| LightGBM training | ✅ best iter 82, no warnings |
| Test PR-AUC ≥ 0.55 (proposal goal) | ✅ **0.66** |
| FWI baseline comparison documented | ✅ +14.8 pts |
| Calibration applied | ✅ isotonic, reliability diagram saved |
| Model artifacts saved | ✅ 4 files under `data/models/wildfire_risk_v1/` |
| API endpoints respond | ✅ `/api/risk/grid` returns 185 cells in < 200 ms |
| Cesium layer renders | ✅ hex grid coloured by risk class |
| Layer toggle, modal, info panel wired | ✅ |
| `pnpm exec tsc -b --noEmit` | ✅ clean |

## Known limitations (carried forward)
- Single Kamloops weather station drives all cell predictions; per-cell variation comes from historical density only.
- No NDVI / fuel-state features yet.
- No lightning data.
- CWFIS upstream still down; we no longer depend on it.

## What's next — Phase 4
The AQ Forecaster (LightGBM quantile, q10/q50/q90 PM2.5 over 48h) is the second ML model in the original plan. **Deferred to Phase 4** because it needs historical hourly PM2.5 data we haven't yet ingested (the BC Air Data Archive bulk-CSV job isn't built yet — adding it makes the AQ dashboard route the natural Phase 4 surface, not a back-pocket forecaster). The endpoint `/api/aq/forecast` continues to return the `not_implemented` stub until then.
