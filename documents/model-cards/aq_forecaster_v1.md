# Model card — `aq_forecaster_v1`

## Intended use
Forecast **hourly PM2.5 concentration (µg/m³) at Kamloops (50.6745 °N, 120.3273 °W)** out to 48 hours ahead, with explicit **uncertainty bounds** at the 10th, 50th, and 90th quantiles. The point forecast is the q50 (median); q10 and q90 render the uncertainty band on the `/air-quality` forecast chart. The band is nominally an 80% interval but measures 57–66% coverage on the holdout — see Calibration below, and read it as a likely range rather than an 80% interval.

**Use this model**: as an informational layer on the WildfireIQ Kamloops platform, alongside (not in place of) Environment and Climate Change Canada's RAQDPS-FW smoke forecast and Health Canada's Air Quality Health Index guidance.

**Do not use this model**: for clinical, occupational-health, regulatory, or insurance decisions; for any setting where a single authoritative source is required; outside the Kamloops region (the model has no spatial component — one location only).

## Training data
- **Target & predictors**: Open-Meteo CAMS air-quality archive at the Kamloops centroid (50.6745°N, 120.3273°W), hourly resolution, co-located with hourly weather (temperature, RH, wind, wind direction, precipitation, boundary-layer height).
- **Corpus**: 11,256 hourly rows spanning 2025-05-28 to 2026-09-08 — 469 days, so the record now contains a full summer smoke season. The nightly `open_meteo_aq_archive` job keeps the file at a rolling year, and `make train-aq` uses whatever it holds; the figures below belong to the 2026-09-08 retrain.
- **Weather**: Open-Meteo GEM-HRDPS-derived hourly weather for the same coordinate.
- **Leakage**: none. Every lag and rolling window is computed strictly causally, and the holdout is the tail of the series.

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
- LightGBM hyper-parameters (`ml/train_aq.py`): 31 leaves, learning rate 0.04, `min_data_in_leaf` 25, feature and bagging fraction 0.85 at frequency 5, L2 1.0, seed 7, **200 boosting rounds, no early stopping**.
- **Why 200 fixed rounds.** The count was swept at 100 / 200 / 300 / 500 on the full-year corpus. All four beat the persistence baseline at the same five horizons; 200 lands within 2% of 500 on test MAE while producing boosters 2.5× smaller (0.57 MB against 1.42 MB, times 21 models — 13 MB against 50 MB committed). Early stopping on a carved-out validation slice was also tried and was worse: it costs 10% of the training data and stopped short, dropping to three horizons better than persistence.
- **Split**: chronological 80% train / 20% holdout, per horizon. The holdout is never used for any fitting decision.

## Held-out test results (q50 MAE vs. persistence baseline)

Retrained 2026-09-08 on 8,979 training rows with a 2,245-row chronological
holdout. Errors are in µg/m³; lower is better.

| Horizon | Model MAE | Persistence MAE | Ratio | Verdict |
|---:|---:|---:|---:|:---|
|  1 h | 4.92 |  2.93 | 1.68 | worse |
|  3 h | 7.43 |  6.73 | 1.10 | worse |
|  6 h | 10.10 | 11.09 | 0.91 | **better** |
| 12 h | 11.35 | 14.37 | 0.79 | **better** |
| 24 h | 11.71 | 12.30 | 0.95 | **better** |
| 36 h | 13.11 | 16.54 | 0.79 | **better** |
| 48 h | 13.62 | 16.27 | 0.84 | **better** |

**The model wins from six hours out, and loses below that.** That split is the
honest headline, and it is a cleaner result than the one this card previously
reported. At one to three hours PM2.5 is so strongly autocorrelated that simply
repeating the current reading is very hard to beat: a tree ensemble smooths the
sharp ramps that arrive with a plume, so it trails persistence exactly where
persistence is strongest. From six hours out that autocorrelation decays, the
weather features start to carry the signal, and the model is 5–21% better —
including 21% at both the 12- and 36-hour marks, the windows a person actually
plans around.

### Comparison with the previous, shorter-corpus figures

The absolute errors here are roughly three times the ones this card reported
before (0.67–3.90 µg/m³). **The models are not worse; the test set is harder.**
The earlier holdout was the tail of a 92-day window that happened to be clean
air, where both the model and the baseline were scoring near sensor noise. The
current holdout contains real smoke events, so both error columns rise together
and the ratio between them is the only figure comparable across the two runs.
By that measure the model beat persistence at five of seven horizons before and
does so again now — but at a more useful set of horizons.


## Pinball loss (quantile regression objective)
The full per-horizon pinball losses for q10/q50/q90 are persisted in `data/models/aq_forecaster_v1/metrics.json`. q10 loss is well under q50 at every horizon (1.20–1.88 against 2.46–6.81), which is what a right-skewed target produces: the 10th percentile of a distribution with a long upper tail is an easy target, the median is not.

## Calibration
The chart's shaded band is the q10 → q90 interval, so by construction it should
contain 80% of observations. **Measured on the holdout, it does not — it contains
57–66%.**

| Horizon | Band coverage | Mean band width |
|---:|---:|---:|
|  1 h | 65.5% | 10.5 µg/m³ |
|  3 h | 60.1% | 11.7 µg/m³ |
|  6 h | 57.5% | 15.3 µg/m³ |
| 12 h | 58.9% | 17.7 µg/m³ |
| 24 h | 59.7% | 17.8 µg/m³ |
| 36 h | 58.9% | 17.3 µg/m³ |
| 48 h | 58.9% | 16.1 µg/m³ |

An earlier version of this card said coverage was "approximately on target"
above six hours. That was not measured, and it was wrong.

The band is therefore **too narrow, and the chart understates uncertainty by
roughly 20 percentage points of coverage.** The cause is ordinary for quantile
gradient boosting on a spiky, right-skewed target: each quantile model is fitted
independently and regularised toward the conditional centre, so the outer
quantiles pull inward. Extreme smoke hours — the ones that matter most — are
exactly where the true value escapes the band.

The fix is not to widen the nominal quantiles, which would relabel the chart
without making it honest, but to calibrate: hold out a slice, measure the
coverage shortfall per horizon, and inflate the interval by the factor that
brings empirical coverage to 80% (split conformal prediction gives this a
finite-sample guarantee). That is the single highest-value improvement
outstanding on this model, and until it is done the band should be read as
"likely range", not as an 80% interval.

## Known failure modes
- **Pacific NW US smoke transport**. The model has no upstream sensor — when a smoke plume arrives from Oregon, Washington, or Idaho the lagged-PM2.5 features can't see it coming until it's already at Kamloops.
- **Pyroconvective injection events**. When a large local fire injects smoke into the boundary layer at non-diurnal times, the model under-predicts the rise.
- **Long-range transport from BC interior fires**. Without a directional wind-trajectory model, the forecaster relies on local wind + boundary-layer features, which is a coarse proxy for transport.
- **Cold-season inversions**. Kamloops valley inversions can pool pollutants overnight in winter. The 469-day corpus now spans one full winter, so these events are represented for the first time, but one winter is a thin sample and the model should not be trusted on them yet.
- **Quantile crossing**. The three quantile models are fitted independently, so nothing guarantees q10 ≤ q50 ≤ q90. `aq_infer` sorts the triple and floors it at zero before serving. On the current holdout no row actually crossed, so the guard is precautionary rather than load-bearing — and it is why measured band coverage is identical with and without it.

## Ethical considerations
- **Health-affecting predictions**: a wrong-and-confident forecast during a smoke event could discourage sensitive individuals from taking precautions. The band is the structural guard against this, and it is currently a weaker guard than its label suggests — measured coverage is 57–66% against a nominal 80%, so the chart and the API both describe it as a likely range rather than an interval. Calibrating it is the top outstanding item on this model.
- **Informational only**: the `/air-quality` page footer and every Health Canada guidance block reiterate that this is not clinical or regulatory guidance. Health Canada's official AQHI remains the canonical source.
- **No PII**: there is no user-specific input to the forecast. Web Notification subscriptions are local-only (`NotifyMe`).

## Reproducibility
- Trainer: `apps/api/wildfireiq_api/ml/train_aq.py`. Deterministic given the input parquet (single seed, no parallel non-determinism in LightGBM at our settings).
- Make target: `make train-aq` (root-level Makefile).
- Inputs: `data/processed/aq_hourly_kamloops.parquet` — Open-Meteo CAMS hourly with co-located weather. `open_meteo_aq_hourly` upserts the recent window every hour; `open_meteo_aq_archive` runs nightly and holds the file at a rolling 365 days. Retraining on a longer file needs no code change, and the corpus span is recorded in this card.
- Outputs: `data/models/aq_forecaster_v1/{features.json, metrics.json, h{H}/q{Q}.txt}` for H ∈ {1,3,6,12,24,36,48}, Q ∈ {10,50,90}. LightGBM native text format.
- Inference: `apps/api/wildfireiq_api/ml/aq_infer.py`, served at `/api/aq/forecast`.

## Not published here
- We do not ship ONNX exports. An exporter existed for the risk classifier and was removed in the September 2026 audit: nothing loaded the artifact at runtime, and it carried four dependencies for a file the API never opened. LightGBM loads a booster in milliseconds in-process, so the export bought portability nobody was using.
- SHAP feature importance is not currently published — the LightGBM `model.feature_importance("gain")` values are persisted in the model artifact metadata for future use.
- 1000-bootstrap CIs on the test MAEs are not currently rendered into a static plot. The raw test predictions are persisted; the bootstrap can be re-run from the trainer.
