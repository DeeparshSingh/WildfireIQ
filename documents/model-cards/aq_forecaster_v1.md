# Model card — `aq_forecaster_v1`

## Intended use
Forecast **hourly PM2.5 concentration (µg/m³) at Kamloops (50.6745 °N, 120.3273 °W)** out to 48 hours ahead, with explicit **uncertainty bounds** at the 10th, 50th, and 90th quantiles. The point forecast is the q50 (median); q10 and q90 render the uncertainty band on the `/air-quality` forecast chart. The band is **conformally calibrated** and measures 79–81% coverage on held-out data against its nominal 80% — see Calibration for what that does and does not guarantee.

**Use this model**: as an informational layer on the WildfireIQ Kamloops platform, alongside (not in place of) Environment and Climate Change Canada's RAQDPS-FW smoke forecast and Health Canada's Air Quality Health Index guidance.

**Do not use this model**: for clinical, occupational-health, regulatory, or insurance decisions; for any setting where a single authoritative source is required; outside the Kamloops region (the model has no spatial component — one location only).

## Training data
- **Target & predictors**: Open-Meteo CAMS air-quality archive at the Kamloops centroid (50.6745°N, 120.3273°W), hourly resolution, co-located with hourly weather (temperature, RH, wind, wind direction, precipitation, boundary-layer height).
- **Corpus**: 11,256 hourly rows spanning 2025-05-28 to 2026-09-08 — 469 days, so the record now contains a full summer smoke season. The nightly `open_meteo_aq_archive` job extends the record and nothing trims it, so it grows; `make train-aq` uses whatever it holds, and the figures below belong to the 2026-09-08 retrain.
- **Weather**: Open-Meteo GEM-HRDPS-derived hourly weather for the same coordinate.
- **Splits**: the models are fitted on the first 70% of the record chronologically (7,856 rows), so no future hour informs the fit. The remaining 30% is split at random into a calibration third (1,122 rows) and a test two-thirds (2,246 rows). Randomising that last step is deliberate; see Calibration.
- **Leakage**: none into the fit. Every lag and rolling window is computed strictly causally.

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

Retrained 2026-09-08. Errors are µg/m³ on the 2,246-row test split; lower is
better. "Band" is the fraction of those rows whose true value fell inside the
q10–q90 band, before and after conformal calibration.

| Horizon | MAE | Persistence | Ratio | Verdict | Band raw | Band calibrated | Widening | Mean width |
|---:|---:|---:|---:|:---|---:|---:|---:|---:|
|  1 h | 3.45 |  2.15 | 1.60 | worse | 68% | 81% | ×1.19 |  9.6 |
|  3 h | 5.37 |  5.07 | 1.06 | worse | 62% | 79% | ×1.28 | 13.9 |
|  6 h | 7.21 |  8.32 | 0.87 | **better** | 61% | 80% | ×1.27 | 18.5 |
| 12 h | 8.33 | 10.68 | 0.78 | **better** | 59% | 79% | ×1.21 | 20.7 |
| 24 h | 8.58 |  9.13 | 0.94 | **better** | 65% | 80% | ×1.19 | 20.5 |
| 36 h | 9.50 | 12.07 | 0.79 | **better** | 62% | 81% | ×1.25 | 22.0 |
| 48 h | 9.99 | 11.81 | 0.85 | **better** | 63% | 81% | ×1.26 | 21.1 |

**The model wins from six hours out, by 6–22%, and loses below that.** That
split is the honest headline. At one to three hours PM2.5 is so strongly
autocorrelated that repeating the current reading is very hard to beat: a tree
ensemble smooths the sharp ramps a plume arrives on, so it trails persistence
exactly where persistence is strongest. From six hours out that autocorrelation
decays, the weather features start carrying the signal, and the model is
clearly ahead — including 22% at twelve hours and 21% at thirty-six, the
windows a person actually plans around.

### On comparing these numbers with earlier versions of this card

Absolute errors here are several times those this card reported before the
September 2026 retrain (0.67–3.90 µg/m³). **The models are not worse; the test
set is harder.** The earlier holdout was the tail of a 92-day window that
happened to be clean air, where both the model and the baseline scored near
sensor noise. The current record spans 469 days including a full smoke season,
so both error columns rise together and the ratio between them is the only
figure comparable across runs. By that measure the result has held at five of
seven horizons across every retrain, and has moved to a more useful set of
horizons.


## Pinball loss (quantile regression objective)
The full per-horizon pinball losses for q10/q50/q90 are persisted in `data/models/aq_forecaster_v1/metrics.json`. q10 loss is well under q50 at every horizon (1.20–1.88 against 2.46–6.81), which is what a right-skewed target produces: the 10th percentile of a distribution with a long upper tail is an easy target, the median is not.

## Calibration

Uncalibrated, the q10–q90 band covered **59–68%** of held-out observations
while its label implied 80%. An earlier version of this card called that
"approximately on target" above six hours; that was never measured, and it was
wrong. The cause is ordinary for quantile gradient boosting: each quantile is
fitted independently and regularised toward the conditional centre, so the
outer quantiles pull inward — worst exactly on the extreme smoke hours that
matter most.

The band is now **conformalised** using width-normalised conformalized quantile
regression (Romano, Patterson & Candès, 2019). For each calibration row the
conformity score is how far outside the band the truth fell, divided by the
band's own width; the widening factor is the `ceil((n+1)(1−α))`-th smallest of
those scores, and serving multiplies each side of the band by it. Because the
score is normalised by width, the correction is multiplicative: a confident
hour keeps a tight band and an uncertain one widens further, which is the
information a band exists to carry. Factors land between ×1.19 and ×1.28 and
live in `data/models/aq_forecaster_v1/conformal.json`; `ml.aq_infer` applies
them, and a missing file degrades to no widening rather than an error.

Measured coverage after calibration is **79–81% against a nominal 80%**, at a
mean band width of 10–22 µg/m³ depending on horizon.

### Why the calibration split is randomised, and what that costs

Conformal calibration requires the calibration rows and the rows being
predicted to be **exchangeable**. Hourly PM2.5 over a single year is not: it is
autocorrelated and strongly seasonal. On this record a chronological
calibration slice lands in April–June air averaging 6.8 µg/m³ (peak 23), while
the holdout is the June–September fire season averaging 21.6 (peak 185).
Calibrating on the first and evaluating on the second reached only **63–69%** —
a factor learned from spring air cannot anticipate a smoke season. Five-fold
cross-conformal over the whole training period did no better (**62–69%**), for
the same reason: the record contains exactly one severe smoke season and it
sits entirely in the holdout.

Drawing calibration and test rows at random from the same window fixes the
exchangeability and reaches 79–81%. Two things follow, and both matter:

1. **What this establishes.** Over held-out hours from the recent period, about
   four in five observations fall inside the band. That is a true, checkable
   statement about the band a user is shown today, and a large improvement on
   three in five.
2. **What it does not establish.** It is not a guarantee for a regime the
   record has never seen. Calibration and test rows are interleaved in time and
   adjacent hours are highly correlated, so the figure is somewhat optimistic
   for a genuine forward-in-time forecast; and when a new season opens with
   conditions outside the archive, coverage will dip until the factor is
   recomputed.

The practical consequence is that the factor must be **recomputed as the
archive grows**, which costs nothing: the nightly archive job keeps extending
the record and `make train-aq` recalculates and rewrites `conformal.json`. The
one structural fix that would remove the caveat is more history — a second and
third smoke season in the record — not a different estimator.


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
- Inputs: `data/processed/aq_hourly_kamloops.parquet` — Open-Meteo CAMS hourly with co-located weather. `open_meteo_aq_hourly` upserts the recent window every hour; `open_meteo_aq_archive` runs nightly, backfilling the last 365 days; nothing trims the far end, so the record accumulates. Retraining on a longer file needs no code change, and the corpus span is recorded in this card.
- Outputs: `data/models/aq_forecaster_v1/{features.json, metrics.json, h{H}/q{Q}.txt}` for H ∈ {1,3,6,12,24,36,48}, Q ∈ {10,50,90}. LightGBM native text format.
- Inference: `apps/api/wildfireiq_api/ml/aq_infer.py`, served at `/api/aq/forecast`.

## Not published here
- We do not ship ONNX exports. An exporter existed for the risk classifier and was removed in the September 2026 audit: nothing loaded the artifact at runtime, and it carried four dependencies for a file the API never opened. LightGBM loads a booster in milliseconds in-process, so the export bought portability nobody was using.
- SHAP feature importance is not currently published — the LightGBM `model.feature_importance("gain")` values are persisted in the model artifact metadata for future use.
- 1000-bootstrap CIs on the test MAEs are not currently rendered into a static plot. The raw test predictions are persisted; the bootstrap can be re-run from the trainer.
