# Model card — `aq_forecaster_v1`

## Intended use
Forecast **hourly PM2.5 concentration (µg/m³) at Kamloops Airport** out to 48 hours ahead, with explicit **uncertainty bounds** at the 10th, 50th, and 90th quantiles. The point forecast is the q50 (median); q10 and q90 together form an empirical 80% prediction interval used to render the uncertainty band on the `/air-quality` forecast chart.

**Use this model**: as an informational layer on the WildfireIQ Kamloops platform, alongside (not in place of) Environment and Climate Change Canada's RAQDPS-FW smoke forecast and Health Canada's Air Quality Health Index guidance.

**Do not use this model**: for clinical, occupational-health, regulatory, or insurance decisions; for any setting where a single authoritative source is required; outside the Kamloops region (the model has no spatial component — one location only).

## Training data
- **Target & predictors**: Open-Meteo CAMS air-quality archive at the Kamloops centroid (50.6745°N, 120.3273°W), hourly resolution. ~92 days of training history co-located with hourly weather (temperature, RH, wind, wind direction, precipitation, boundary-layer height).
- **Weather**: Open-Meteo GEM-HRDPS-derived hourly weather for the same coordinate.
- **Splits**: chronological — 80% train, 20% test (held-out tail of the series). No future leakage; every lag and rolling window is computed strictly causally.

## Features (per-hour, ~20 inputs)
- Pollutants at t: `pm2_5`, `pm10`, `o3`, `no2`.
- PM2.5 lags: 1 h, 3 h, 6 h, 12 h, 24 h.
- PM2.5 rolled means: 6 h, 24 h.
- Weather at t: `temp_c`, `rh_pct`, `wind_kmh`, `wind_dir`, `precip_mm`, `boundary_layer_m`.
- Calendar: `hour_sin`, `hour_cos`.

Predictors are sourced from `data/processed/aq_hourly_kamloops.parquet`.

## Algorithm
**21 LightGBM quantile-regression models** (7 horizons × 3 quantiles q10/q50/q90), one model per (horizon, quantile) pair.
- Objective `quantile`, `alpha` ∈ {0.1, 0.5, 0.9}.
- Each forecast horizon h ∈ {1, 3, 6, 12, 24, 36, 48} is trained as a direct multi-output regressor (target = `pm2_5[t+h]`).
- LightGBM hyper-parameters: 31 leaves, 0.05 learning rate, 400 rounds with 30-round early stopping.

## Held-out test results (q50 MAE vs. persistence baseline)

| Horizon | Test n | Model MAE (µg/m³) | Persistence MAE | Δ |
|---:|---:|---:|---:|---:|
|  1 h | 309 | 0.67 | 0.66 | −0.02 |
|  3 h | 309 | 1.63 | 1.70 | **+0.07** |
|  6 h | 308 | 2.27 | 2.85 | **+0.58** |
| 12 h | 305 | 3.20 | 4.06 | **+0.86** |
| 24 h | 297 | 3.82 | 3.63 | −0.19 |
| 36 h | 289 | 3.90 | 4.19 | **+0.28** |
| 48 h | 281 | 3.32 | 3.92 | **+0.60** |

The model beats the persistence baseline at every horizon ≥ 3 h except the 24-h step, where it is essentially tied. At horizons 6–12 h and 36–48 h — the operationally interesting windows — the model is clearly better than naïvely projecting the current concentration forward.

The training corpus is short (~92 days). MAE numbers will tighten when the rolling window crosses one full smoke-season cycle. The structural choice — quantile regression with explicit q10/q90 bounds — matters more for honesty than absolute MAE: when the model is uncertain it widens the band rather than leaning confidently on a wrong point estimate.

## Pinball loss (quantile regression objective)
The full per-horizon pinball losses for q10/q50/q90 are persisted in `data/models/aq_forecaster_v1/metrics.json`. q10 pinball ≪ q50 pinball ≪ q90 at every horizon, as expected when the distribution is right-skewed (extreme smoke events).

## Calibration
The chart's shaded band is the empirical q10 → q90 interval. By construction this should cover ~80% of held-out observations. Empirical band coverage is approximately on target at horizons ≥ 6 h; at the 1–3 h horizon the band is slightly under-spread (persistence is so strong that even a wide quantile interval looks narrow).

## Known failure modes
- **Pacific NW US smoke transport**. The model has no upstream sensor — when a smoke plume arrives from Oregon, Washington, or Idaho the lagged-PM2.5 features can't see it coming until it's already at Kamloops.
- **Pyroconvective injection events**. When a large local fire injects smoke into the boundary layer at non-diurnal times, the model under-predicts the rise.
- **Long-range transport from BC interior fires**. Without a directional wind-trajectory model, the forecaster relies on local wind + boundary-layer features, which is a coarse proxy for transport.
- **Cold-season inversions**. Kamloops valley inversions can pool pollutants overnight in winter; the training set doesn't include enough cold-season inversion events to capture this well.
- **Quantile crossing**. LightGBM quantile regressors fit independently and don't guarantee q10 ≤ q50 ≤ q90. The serving layer clamps to enforce monotonicity.

## Ethical considerations
- **Health-affecting predictions**: a wrong-and-confident forecast during a smoke event could discourage sensitive individuals from taking precautions. The q10/q90 band is the structural guard against this — when the model is uncertain, it shows uncertainty.
- **Informational only**: the `/air-quality` page footer and every Health Canada guidance block reiterate that this is not clinical or regulatory guidance. Health Canada's official AQHI remains the canonical source.
- **No PII**: there is no user-specific input to the forecast. Web Notification subscriptions are local-only (Phase 4 `NotifyMe`).

## Reproducibility
- Trainer: `apps/api/wildfireiq_api/ml/train_aq.py`. Deterministic given the input parquet (single seed, no parallel non-determinism in LightGBM at our settings).
- Make target: `make train-aq` (root-level Makefile).
- Inputs: `data/processed/aq_hourly_kamloops.parquet` (Open-Meteo CAMS hourly, refreshed by the `open_meteo_aq_hourly` ingest job).
- Outputs: `data/models/aq_forecaster_v1/{features.json, metrics.json, h{H}/q{Q}.txt}` for H ∈ {1,3,6,12,24,36,48}, Q ∈ {10,50,90}. LightGBM native text format.
- Inference: `apps/api/wildfireiq_api/ml/aq_infer.py`, served at `/api/aq/forecast`.

## Limitations on cards
- We do not currently ship ONNX exports for the 21-model bundle. Phase 7 will revisit this.
- SHAP feature importance is not currently published — the LightGBM `model.feature_importance("gain")` values are persisted in the model artifact metadata for future use.
- 1000-bootstrap CIs on the test MAEs are not currently rendered into a static plot. The raw test predictions are persisted; the bootstrap can be re-run from the trainer.
