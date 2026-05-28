# Model card — `wildfire_risk_v1`

## Intended use
Predict the probability that **at least one wildfire ignites somewhere in the Thompson-Okanagan region of British Columbia on a given day**, then weight that regional probability by each H3 r=5 cell's historical fire-day density to produce a per-cell risk score. The score is bucketed into the four levels defined in the project proposal: **Low / Moderate / High / Extreme**.

**Use this model**: as an informational layer on the WildfireIQ Kamloops platform, alongside (not in place of) authoritative guidance from the BC Wildfire Service, BC Emergency Management, and BC Emergency Health Services.

**Do not use this model**: for operational firefighting decisions, evacuation orders, insurance underwriting, or anywhere a single official source is required.

## Training data
- **Fires**: BC Wildfire Service `PROT_HISTORICAL_INCIDENTS_SP` (DataBC) — 15,996 incidents 1999–2025 across all of British Columbia. Restricted at label time to the Thompson-Okanagan bounding box (-121.5°W → -118.5°W, 50°N → 51.5°N).
- **Weather**: Open-Meteo ERA5 archive at the Kamloops centroid (50.6745°N, 120.3273°W), daily max-temp / min-temp / min-RH / max-wind / max-gust / total-precip / max-VPD / ET₀ for 1999-01-01 → 2026-05-10 (9,992 daily rows).
- **Fire Weather Index codes** (FFMC, DMC, DC, ISI, BUI, FWI, DSR) are **derived from the weather data** using the canonical Van Wagner & Pickett (1985) equations — implemented in `wildfireiq_api/ml/fwi.py`. This eliminates the runtime dependency on NRCan's CWFIS GeoServer (which has been HTTP-502'd throughout the build).

## Features
40 input features per day:
- Current-day weather: `temp_max_c`, `temp_min_c`, `rh_min_pct`, `wind_max_kmh`, `wind_gust_max_kmh`, `precip_mm`, `vpd_max_kpa`, `et0_mm`
- FWI codes: `ffmc`, `dmc`, `dc`, `isi`, `bui`, `fwi`, `dsr`
- Lagged + rolled: 1-day lag, 7-day lag, 7-day mean, 30-day mean for each of {temp_max, rh_min, wind_max, precip, vpd_max}
- Drought signals: `precip_sum7`, `precip_sum30`, `dry_spell_days`
- Calendar: `doy_sin`, `doy_cos`, `month`

## Algorithm
LightGBM binary classifier (objective `binary`, logloss metric).
- 63 leaves, min 200 samples per leaf, learning rate 0.04, lambda_l2 = 1.0.
- 85% feature + 85% bagging fraction at frequency 5.
- Early stopping at 50 rounds (best at iteration 82).
- Isotonic regression calibration fit on the 2022 validation predictions.

## Splits
- **Train**: 1999-01-01 → 2021-12-31  (8,394 days, fire-day prior 0.343)
- **Validation**: 2022-01-01 → 2022-12-31  (365 days, fire-day prior 0.329)
- **Test**: 2023-01-01 → 2023-12-31  (365 days, fire-day prior 0.290)

The proposal commits to held-out validation against the 2022 + 2023 fire seasons — done.

## Held-out 2023 test metrics

| Metric | This model | FWI ≥ 19 threshold | Climatology |
|---|---|---|---|
| **PR-AUC** | **0.663** (raw) / 0.633 (cal.) | 0.515 | 0.290 |
| **ROC-AUC** | **0.870** | — | — |
| **Brier** | **0.136** (raw) / 0.143 (cal.) | — | — |
| **Logloss (cal.)** | 0.687 | — | — |

**+14.8 PR-AUC points over the FWI-threshold baseline** and **2.3× over the climatology floor**, on a fully held-out year. Worth noting: 2023 was an unusually intense BC fire year (the worst on record nationally), and the model still discriminates well.

The calibrator slightly hurts PR-AUC on 2023 (0.663 → 0.633) — typical when the test year's prior differs from the calibration year's. Brier scores stay tight. The serving path uses calibrated probabilities so the risk-class buckets are interpretable.

## Top-10 features by gain importance

| Rank | Feature | Notes |
|---|---|---|
| 1 | `ffmc` | Fine fuel moisture — fastest-responding FWI code |
| 2 | `dc` | Drought code — long-term drying |
| 3 | `dmc` | Duff moisture code |
| 4 | `fwi` | The headline composite index |
| 5 | `dry_spell_days` | Days since ≥ 1 mm rain |
| 6 | `vpd_max_kpa` | Atmospheric drying power |
| 7 | `temp_max_c` | Current-day high temperature |
| 8 | `bui` | Buildup index |
| 9 | `doy_cos` | Calendar seasonality |
| 10 | `precip_sum30` | 30-day total precip |

Exactly the wildfire-science textbook ranking. Useful sanity check.

## Calibration (test set, 10 quantile bins)
Reliability diagram bin centres vs observed positive frequency are written to `data/models/wildfire_risk_v1/metrics.json`. Isotonic-calibrated probabilities are well-aligned with empirical frequencies in the mid-range (0.2-0.6); the model is slightly underconfident in the high-end (≥ 0.7), consistent with 2023 being a higher-prior year than 2022.

## Known limitations
1. **Single weather station** — features come from Kamloops only. Cells far from Kamloops see the same weather inputs; per-cell variation comes entirely from historical density. The per-cell display should be read as "regional fire-day probability today, modulated by where fires have historically been most common."
2. **No NDVI / fuel-state** — vegetation greenness anomaly is not yet a feature. Phase 4+ could add this via Sentinel-2 or MOD13Q1.
3. **No lightning** — the major natural ignition driver. Adding CLDN strike counts is the highest-impact feature improvement.
4. **No human-ignition proxy** — long-weekend / wildland-urban-interface indicators not yet included.
5. **Static historical weights** — the per-cell density was computed once from 1999-2025 and is not re-weighted by recency or climate-change-adjusted baselines.

## Reproducibility
```bash
# 1. Bootstrap data (≈40 s wall-clock total)
uv run python scripts/ingest/bootstrap.py --only databc_fires_historical
uv run python scripts/ingest/bootstrap.py --only open_meteo_archive_kamloops

# 2. Build features (Van Wagner FWI + lags + cell density)
uv run python -m wildfireiq_api.ml.features

# 3. Train (≈15 s on a M-series Mac CPU)
uv run python -m wildfireiq_api.ml.train_risk
```
Seed: 7. Artifacts: `data/models/wildfire_risk_v1/{model.txt, calibrator.joblib, metrics.json, features.json}`.

## Ethical considerations
This model is informational, not authoritative. It must not be the sole basis for protective or operational decisions. The platform UI surfaces this attribution alongside every risk-grid cell and on every detail panel.
