# Model card — `wildfire_risk_v1`

## Intended use
Predict the probability that **at least one wildfire ignites somewhere in a modelled region of British Columbia on a given day**, then weight that regional probability by each H3 r=5 cell's historical fire-day density to produce a per-cell risk score. The score is bucketed into the four levels defined in the project proposal: **Low / Moderate / High / Extreme**.

Four regions are modelled, each scored from its own weather:

| Region | Anchor city (weather sampled here) | Bounding box | Cells |
|---|---|---|---:|
| Thompson-Okanagan | Kamloops (50.6745 °N, 120.3273 °W) | −121.5 → −118.5 °W, 50.0 → 51.5 °N | 185 |
| Prince George (Cariboo) | Prince George (53.9171 °N, 122.7497 °W) | −124.2 → −121.5 °W, 53.0 → 54.6 °N | 166 |
| Lower Mainland | Vancouver (49.2497 °N, 123.1193 °W) | −123.6 → −121.6 °W, 49.0 → 49.9 °N | 87 |
| Central Okanagan | Kelowna (49.8880 °N, 119.4960 °W) | −120.6 → −118.5 °W, 49.0 → 50.0 °N | 85 |

The region list lives in `wildfireiq_api/constants.py::REGIONS` and is read by the weather job, the feature builder, inference, and the tests, so it is the single source of truth.

**Use this model**: as an informational layer on the WildfireIQ Kamloops platform, alongside (not in place of) authoritative guidance from the BC Wildfire Service, BC Emergency Management, and BC Emergency Health Services.

**Do not use this model**: for operational firefighting decisions, evacuation orders, insurance underwriting, or anywhere a single official source is required.

## Training data
- **Fires**: BC Wildfire Service `PROT_HISTORICAL_INCIDENTS_SP` (DataBC) — 96,356 incidents 1999–2026 across all of British Columbia. Each region filters this province-wide record to its own bounding box at label time. The DataBC download was always province-wide, so covering four regions instead of one added no upstream cost.
- **Weather**: Open-Meteo ERA5 archive sampled at each region's anchor city — daily max-temp / min-temp / min-RH / max-wind / max-gust / total-precip / max-VPD / ET₀ from 1999-01-01, roughly 10,100 daily rows per region. ERA5 lags about five days, so a 15-day forecast tail is spliced on and the series always reaches today.
- **Fire Weather Index codes** (FFMC, DMC, DC, ISI, BUI, FWI, DSR) are **derived from the weather data** per region using the canonical Van Wagner & Pickett (1985) equations — implemented in `wildfireiq_api/ml/fwi.py`. This eliminates the runtime dependency on NRCan's CWFIS GeoServer (which has been HTTP-502'd throughout the build).

## Features
42 input features per region-day (`features_risk_daily.parquet`, 40,368 rows):
- Current-day weather: `temp_max_c`, `temp_min_c`, `rh_min_pct`, `wind_max_kmh`, `wind_gust_max_kmh`, `precip_mm`, `vpd_max_kpa`, `et0_mm`
- FWI codes: `ffmc`, `dmc`, `dc`, `isi`, `bui`, `fwi`, `dsr`
- Lagged + rolled: 1-day lag, 7-day lag, 7-day mean, 30-day mean for each of {temp_max, rh_min, wind_max, precip, vpd_max}
- Drought signals: `precip_sum7`, `precip_sum30`, `dry_spell_days`
- Calendar: `doy_sin`, `doy_cos`, `month`, `year`
- Regional base rate: `region_fire_rate`

`region_fire_rate` is the fraction of days on which that region recorded a fire, computed from **1999–2021 only** (`features.BASE_RATE_MAX_YEAR = 2021`). Restricting it to the training span is what keeps the validation and test years genuinely unseen — a rate computed over the full record would leak the outcome of 2022 and 2023 backwards into training.

## Algorithm
One LightGBM binary classifier (objective `binary`, logloss metric) trained on all four regions **pooled**, not four separate models.

Pooling was chosen for two reasons. First, the relationship between dryness and ignition is the same physics everywhere, so pooling gives the model four times the evidence for it; measured against the earlier single-region model, pooling *raised* Thompson-Okanagan held-out 2023 PR-AUC from 0.66 to 0.72, so this is not a trade of accuracy for coverage. Second, `region_fire_rate` lets the model keep the regions apart, so wet coastal Vancouver is not scored as if it were the dry Interior.

Hyperparameters (`ml/train_risk.py`):
- 63 leaves, min 200 samples per leaf, learning rate 0.04, `lambda_l2` = 1.0.
- 85% feature + 85% bagging fraction at frequency 5.
- Early stopping at 50 rounds (best at iteration 130).
- Isotonic regression calibration fit on the 2022 validation predictions.
- Seed 7.

## Splits
Split by calendar year, applied identically to every region:

- **Train**: 1999-01-01 → 2021-12-31 (33,576 region-days)
- **Validation**: 2022-01-01 → 2022-12-31 (1,460 region-days)
- **Test**: 2023-01-01 → 2023-12-31 (1,460 region-days)

The proposal commits to held-out validation against the 2022 + 2023 fire seasons — done.

## Held-out 2023 test metrics

Reported **per region**, because a single pooled average would let a strong region mask a weak one:

| Region | Fire-days | Base rate | PR-AUC | FWI ≥ 19 threshold | Verdict |
|---|---:|---:|---:|---:|---|
| Thompson-Okanagan | 106 | 0.290 | **0.72** | 0.37 | +35 points |
| Prince George | 67 | 0.184 | **0.61** | 0.37 | +24 points |
| Central Okanagan | 64 | 0.175 | **0.51** | 0.37 | +14 points |
| Lower Mainland | 35 | 0.096 | 0.29 | 0.37 | below baseline |

Pooled across all four regions:

| Metric | This model | FWI ≥ 19 threshold | Climatology |
|---|---|---|---|
| **PR-AUC** | **0.583** (raw) / 0.549 (cal.) | 0.367 | 0.186 |
| **ROC-AUC** | **0.874** | — | — |
| **Brier** | **0.108** (raw) / 0.108 (cal.) | — | — |
| **Logloss (cal.)** | 0.352 | — | — |

Worth noting: 2023 was an unusually intense BC fire year (the worst on record nationally), and the model still discriminates well in the Interior.

The calibrator costs a little pooled PR-AUC (0.583 → 0.549) while leaving Brier unchanged. That is the expected trade: it gives up a little ranking sharpness for probabilities that mean what they say, which is what a four-colour risk scale needs. The serving path uses calibrated probabilities.

## Top-10 features by gain importance

| Rank | Feature | Notes |
|---|---|---|
| 1 | `dmc` | Duff moisture code — medium-term drying |
| 2 | `bui` | Buildup index |
| 3 | `vpd_max_kpa_mean7` | 7-day mean atmospheric drying power |
| 4 | `et0_mm` | Reference evapotranspiration |
| 5 | `wind_max_kmh_mean30` | 30-day mean wind |
| 6 | `doy_cos` | Calendar seasonality |
| 7 | `region_fire_rate` | Which region this row is |
| 8 | `temp_max_c_mean7` | 7-day mean high temperature |
| 9 | `vpd_max_kpa_mean30` | 30-day mean VPD |
| 10 | `rh_min_pct_mean7` | 7-day mean minimum humidity |

Moisture and drying dominate and seasonality follows, which matches the wildfire-science literature. The base-rate term landing seventh rather than first is the result worth checking: it is informative about which region a row belongs to without becoming a shortcut that lets the model ignore the weather.

## Serving

Per request, `ml/risk_infer.py::predict_grid()` loops the regions, scores each from its own weather archive's latest state, multiplies by each cell's `weight` from `cell_density.parquet`, and buckets the result.

Two serving details are worth recording because both were bugs first:

- **Every H3 cell belongs to exactly one region.** Thompson-Okanagan and Central Okanagan share an edge at 50.0 °N. The feature builder walks `REGIONS` in order and the first region to claim a cell keeps it, so a hexagon is never drawn twice in two different colours. `tests/test_risk_regions.py` asserts zero duplicates.
- **A region's headline class is derived from its rendered cells**, not from its raw FWI: it is the highest class covering at least 15% of the region's cells (`_region_risk_level`). Vancouver's FWI of 25.6 exceeds the CFFDRS Extreme threshold of 21, yet nearly all its hexagons render Low or Moderate because its historical density is small. Deriving the badge from the cells keeps the card from contradicting the map.

## Calibration (test set, quantile bins)
Reliability-diagram bin centres versus observed positive frequency are written to `data/models/wildfire_risk_v1/metrics.json` (7 populated bins). Isotonic-calibrated probabilities track empirical frequencies closely from 0.1 to 0.45 and run slightly underconfident above 0.5, consistent with 2023 being a higher-prior year than the 2022 calibration year.

### Why two regions sometimes show the identical probability

Isotonic calibration is a step function, and this one has 48 distinct output
levels. Regions whose *raw* scores fall inside one step come out with the same
calibrated probability to full precision. On 2026-09-04, for instance, Central
Okanagan, the Lower Mainland and Prince George had raw scores of 0.2557, 0.2575
and 0.2582 and all three reported 0.265.

That looks like a bug and is not one. Over the last 60 days the mean
same-day spread between the four regions is 0.53, they were never all equal on
any day, and their 60-day means are far apart (Thompson-Okanagan 0.74, Central
Okanagan 0.60, Lower Mainland 0.25, Prince George 0.22). The collapse only
happens between regions that genuinely scored within a few thousandths of each
other, and it is the price of calibrated probabilities, which a four-colour risk
scale needs more than it needs fine-grained ordering between regions.

## Known limitations
1. **One weather series per region, not per cell.** Each region reads its own anchor-city ERA5 series, but cells within a region share it, so per-cell variation comes entirely from historical density. A per-cell display should be read as "this region's fire-day probability today, modulated by where fires have historically been most common."
2. **The Lower Mainland underperforms its own FWI baseline** (0.29 vs 0.37). It is a genuinely low-event area — 35 fire-days in the test year against Thompson-Okanagan's 106 — which makes it both correctly low-risk and the hardest region to rank. This is disclosed in the UI rather than averaged away, and it is the clearest candidate for a region-specific model if coastal coverage becomes a priority.
3. **No NDVI / fuel-state.** Vegetation greenness anomaly is not a feature; Sentinel-2 or MOD13Q1 could supply it.
4. **No lightning.** The major natural ignition driver. Adding CLDN strike counts remains the highest-impact feature improvement.
5. **No human-ignition proxy.** Long-weekend and wildland-urban-interface indicators are not included.
6. **Static historical weights.** Per-cell density is computed from the full 1999–2026 record and is not re-weighted by recency or adjusted for a shifting climate baseline.

## Reproducibility
```bash
# 1. Bootstrap the province-wide fire record and the Kamloops archive
uv run python scripts/ingest/bootstrap.py --only databc_fires_historical
uv run python scripts/ingest/bootstrap.py --only open_meteo_archive_kamloops

# 2. Build the other three regions' weather archives
make region-weather

# 3. Build features (per-region Van Wagner FWI + lags + cell density)
make risk-features

# 4. Train (≈20 s on an M-series Mac CPU)
uv run python -m wildfireiq_api.ml.train_risk
```
Steps 2 and 3 are also wired as nightly jobs (`derived_region_weather` at 02:25, `derived_risk_features` at 02:35), and `derived_risk_features` declares `depends_on` so the startup catch-up can never run it before the weather archives it reads.

Seed: 7. Artifacts: `data/models/wildfire_risk_v1/{model.txt, calibrator.joblib, metrics.json, features.json}`.

## Ethical considerations
This model is informational, not authoritative. It must not be the sole basis for protective or operational decisions. The platform UI surfaces this attribution alongside every risk-grid cell and on every detail panel, and it names the region a cell belongs to so a reader is never shown one region's figures for another region's hexagon.
