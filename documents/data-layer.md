# WildfireIQ — Data Layer Reference

A plain-language, per-layer reference for **where every number on this platform comes from, how often it updates, how it's computed, and how accurate it is**. Written so a non-technical reader can follow it.

> **One rule above all:** this platform is **informational**. It is not a substitute for the BC Wildfire Service, BC Emergency Management Climate Readiness, or Environment and Climate Change Canada. When those agencies say something, they win.

---

## How "freshness" works here

When you open the app, the backend immediately checks every data source and refreshes anything older than 30 minutes — so you're looking at current data within seconds of launch, without waiting for the next scheduled update. After that, each source refreshes on its own clock (the cadences below), and the map quietly re-fetches in the background.

| Stage | What happens |
|---|---|
| App launch | Backend runs a "refresh anything stale" pass across all sources |
| Steady state | Each source re-pulls on its cron cadence (see per-layer tables) |
| In the browser | Each map layer re-fetches every 1–30 min depending on how fast the data changes |

---

## 1. Active Fires

| | |
|---|---|
| **What it shows** | Every wildfire the BC Wildfire Service currently reports. Big fires show their mapped burned-area outline; small fires show a flame marker. |
| **Where the data comes from** | BC government open data (DataBC WFS — the `PROT_CURRENT_FIRE_POLYS_SP` and `PROT_CURRENT_FIRE_PNTS_SP` layers). |
| **How often it updates** | Pulled every **15 minutes**; the map re-checks every **60 seconds**. |
| **How it's computed** | No modelling. We download the official list, hide fires marked "Out" by default (toggleable), and draw the rest exactly as published. |
| **Accuracy** | This *is* the authoritative source — it's the same data BCWS shows on its own dashboard. |
| **Known limits** | Fire sizes lag reality slightly because perimeters are re-mapped periodically, not continuously. |

---

## 2. Satellite Hotspots

| | |
|---|---|
| **What it shows** | Spots that satellites measured as unusually hot in the last 72 hours. A "heat alarm," **not** a confirmed fire. Dot size and colour scale with how much heat was radiated (Fire Radiative Power). |
| **Where the data comes from** | NASA FIRMS near-real-time feed — three sensors: VIIRS-NOAA20, VIIRS-SNPP, and MODIS. |
| **How often it updates** | Pulled every **30 minutes**; the map re-checks every **5 minutes**. (Satellites themselves only pass over a few times a day.) |
| **How it's computed** | We download the raw detections for the BC bounding box and drop low-confidence ones (confidence < 30). Everything else is plotted at its reported latitude/longitude. |
| **Accuracy** | Position accuracy is roughly **375 m (VIIRS)** to **1 km (MODIS)** — the satellite's pixel size. A single fire commonly lights up 2–3 neighbouring pixels at the same minute; that's expected, not a duplicate bug. |
| **Known limits** | Industrial gas flares, hot rooftops, and processing plants can also trip the heat sensor. A hotspot means "worth investigating," not "confirmed fire." |

> **About the two dots you saw near each other** (≈ 56.99 °N, −121.08 °W, both confidence 100, same minute): that's two adjacent MODIS pixels reading hot on the same fire front in the Peace River region of northern BC. Both are real, legitimate detections — the fire simply spans more than one 1 km pixel. The hotspot layer covers all of BC, which is why detections appear far north of the Thompson-Okanagan.

---

## 3. Evacuation Zones

| | |
|---|---|
| **What it shows** | Areas under an evacuation **Order** (leave now, red), **Alert** (be ready, amber/dashed), or **Rescind** (safe again, green). |
| **Where the data comes from** | BC Emergency Management Climate Readiness (their public ArcGIS FeatureServer). |
| **How often it updates** | Pulled every **5 minutes**; the map re-checks every **60 seconds**. |
| **How it's computed** | Drawn exactly as issued. We separate the *lifecycle* status (Order/Alert/Rescind) from the *hazard type* (Fire/Flood/Landslide). The Preparedness Hub reuses these polygons to answer "is my address inside a zone?" using a precise point-in-polygon test. |
| **Sorting & hiding** | The in-panel list is sorted **newest issued first**. A **Hide past** control removes rescinded zones from both the list and the map (on by default). |
| **Accuracy** | Authoritative — these are the legal evacuation boundaries. |
| **Known limits** | Boundary geometry is as precise as what the agency publishes. Always confirm with your local authority. |

---

## 4. Fire Weather Index (FWI)

| | |
|---|---|
| **What it shows** | A fire-danger score from the weather at ~18 BC towns. Higher = conditions more primed for fast, intense fire. It describes *weather*, not whether a fire exists. |
| **Where the data comes from** | We calculate it ourselves from Open-Meteo weather, using **Canada's official FWI equations** (the Van Wagner / CFFDRS method). The official NRCan CWFIS service is preferred but was unreachable through most of the build, so the in-house calculation is the working source. |
| **How often it updates** | Recalculated every **30 minutes**; the map re-checks every **10 minutes**. |
| **How it's computed** | For each station we pull the last 30 days of daily weather (temperature, humidity, wind, rain), then run the standard chain of sub-indices in order: **FFMC → DMC → DC → ISI → BUI → FWI → DSR**. The 30-day run-up matters because the index has "memory" — a long dry spell pushes the score up even on a calm day. |
| **Accuracy** | Same equations Canada uses, so the *method* is industry-standard. The small differences vs. official station readings come from using gridded weather instead of the exact on-site instrument. |
| **Known limits** | Station list is representative, not exhaustive. When the official CWFIS feed is reachable, its values take priority over ours. |

### What is the Fire Weather Index?

The **Fire Weather Index (FWI)** is Canada's national fire-danger rating — the same system that produces the "Low / Moderate / High / Extreme" fire-danger signs you see on highways. It turns four weather inputs (temperature, relative humidity, wind speed, and 24-hour rainfall) into a single number that estimates **how intensely a fire would burn and spread if one started today**.

It's built from six sub-codes, each tracking a different fuel layer:

| Code | Full name | Tracks |
|---|---|---|
| FFMC | Fine Fuel Moisture Code | Dryness of surface litter (fast to dry, fast to wet) |
| DMC | Duff Moisture Code | Moisture in loosely-packed organic layers |
| DC | Drought Code | Deep, slow-drying organic matter — the seasonal drought signal |
| ISI | Initial Spread Index | Expected rate of fire spread (combines FFMC + wind) |
| BUI | Buildup Index | Total fuel available to burn (combines DMC + DC) |
| **FWI** | **Fire Weather Index** | **The headline number — combines ISI + BUI** |

A higher FWI doesn't mean a fire is happening — it means the *conditions* for a serious fire are in place. WildfireIQ also shows the official **CFFDRS Fire Danger class** (Low ≤ 1, Moderate 2–4, High 5–12, Very High 13–20, Extreme ≥ 21) so you can read the number the way BCWS does.

---

## 5. Smoke Forecast

| | |
|---|---|
| **What it shows** | Canada's official forecast for wildfire smoke — specifically **PM2.5**, the fine airborne particles in smoke that are most harmful to breathe. A shaded overlay shows where smoke is predicted, hour by hour, for ~3 days. |
| **Where the data comes from** | Environment and Climate Change Canada's **RAQDPS-FW** smoke model, served as map tiles via MSC GeoMet. The per-hour Kamloops number is joined from Open-Meteo's CAMS PM2.5 forecast. |
| **How often it updates** | Pulled every **6 hours**; the map re-checks every **30 minutes**. |
| **How it's computed** | We read the model's forecast window and break it into ~73 hourly snapshots. Each snapshot is paired with the predicted Kamloops PM2.5 value so you see a real number (in µg/m³) even when the overlay looks faint. |
| **Accuracy** | The overlay is Canada's official operational smoke model. The Kamloops readout is a point forecast and will differ from a real sensor by some margin. |
| **Known limits** | When the air is clean the overlay is nearly invisible — that's the truth, not a glitch. PM2.5 is the dominant smoke health signal but not the only pollutant. |

### What is PM2.5?

**PM2.5** means particulate matter smaller than 2.5 microns — about 1/30th the width of a human hair. These particles lodge deep in the lungs and are the main reason wildfire smoke is dangerous. It's measured in **µg/m³** (micrograms per cubic metre of air). Roughly: under 12 is good, 12–35 is moderate, and above 35 starts to matter for sensitive people.

---

## 6. AI Wildfire Risk Grid

| | |
|---|---|
| **What it shows** | Our AI's estimate of wildfire risk across the region today, drawn as coloured hexagons (Low / Moderate / High / Extreme). |
| **Where the data comes from** | An in-house machine-learning model trained on **23 years** of BC Wildfire Service fire records (15,996 incidents) plus matching ERA5 reanalysis weather. |
| **How often it updates** | Recalculated **daily** on the latest weather; the map re-checks every **30 minutes**. The underlying weather series is refreshed to *today* on every app launch. |
| **How it's computed** | Two ingredients multiplied together: **(a)** a region-wide probability that *at least one* fire ignites today, predicted by the model from today's weather + FWI codes; **(b)** each hexagon's historical fire frequency. Cell risk = regional probability × that cell's normalised historical density, then bucketed into the four classes. |
| **Accuracy** | Trained on 1999–2021, tuned on 2022, and **tested on 2023 — a year the model never saw**. On that unseen year it scored **PR-AUC 0.66**, clearly beating the traditional FWI-threshold method (**0.52**) by about 15 points. (PR-AUC measures how well it ranks true fire days above non-fire days; higher is better.) |
| **Honest limits** | The hexagon-to-hexagon difference comes from each area's *fire history*, not from separate local weather — we use one regional weather signal, so two neighbouring hexagons differ only by their past. Alongside every hexagon we also show the deterministic government **CFFDRS Fire Danger** class so you can sanity-check the AI against the standard. |

### How the model actually works (step by step)

1. **Training data.** For every day from 1999 to 2021 we built a row of ~40 features: today's weather (temperature, humidity, wind, rain, vapour-pressure deficit), the six FWI codes, lagged and rolling versions (7-day and 30-day windows), drought signals (days since rain), and calendar terms (day-of-year). The label is simply: did a fire ignite in the region that day?
2. **Algorithm.** A **LightGBM** gradient-boosted tree classifier (≈ 8,394 training days). It outputs a calibrated probability between 0 and 1.
3. **Calibration.** Raw model scores are passed through isotonic regression so a "0.7" really means roughly a 70% chance — important for honest risk colours.
4. **Validation discipline.** We never let the model see 2022 or 2023 during training. Testing on those held-out years is what makes the 0.66 number trustworthy rather than memorised.
5. **Per-cell step.** The single regional probability is scaled by each H3 hexagon's historical fire count (square-root-normalised so a few extreme cells don't dominate), then bucketed Low/Moderate/High/Extreme.

Full detail and reliability diagrams: [`model-cards/wildfire_risk_v1.md`](./model-cards/wildfire_risk_v1.md).

---

## 7. Air Quality Monitor (the `/air-quality` page)

| | |
|---|---|
| **What it shows** | Live Air Quality Health Index (AQHI), a 48-hour PM2.5 forecast with an uncertainty band, a six-pollutant breakdown, a year-long smoke calendar, and Health Canada guidance. |
| **Where the data comes from** | Live AQHI from ECCC GeoMet; pollutant breakdown from WAQI; hourly PM2.5 history + forecast inputs from Open-Meteo CAMS. |
| **How often it updates** | Live AQHI every **hour**; pollutant feed every **hour**; the AQ history archive refreshes nightly to keep a rolling 365-day calendar. |
| **How the forecast is computed** | A second in-house model: **21 LightGBM quantile regressors** (7 forecast horizons × 3 quantiles — 10th, 50th, 90th percentile). The 50th is the central forecast; the 10th–90th band is the honest uncertainty range shown on the chart. |
| **Accuracy** | The forecaster beats the naïve "tomorrow = today" persistence baseline at the 6-, 12-, 36-, and 48-hour horizons. Full per-horizon error table: [`model-cards/aq_forecaster_v1.md`](./model-cards/aq_forecaster_v1.md). |
| **Known limits** | One location (Kamloops). It can't see a smoke plume coming from across the US border until the lagged readings start to rise. |

### What is AQHI?

The **Air Quality Health Index** is Health Canada's 1-to-10+ scale for how risky the current air is to breathe. 1–3 = Low risk, 4–6 = Moderate, 7–10 = High, 10+ = Very High. During wildfire smoke it's driven mostly by PM2.5. WildfireIQ computes the PM2.5 contribution with Health Canada's formula: `(1000 / 10.4) × (exp(0.000487 × PM2.5) − 1)`.

The **smoke calendar** colours each of the last 365 days by that day's worst AQHI, so you can spot smoke seasons at a glance. (It reads a full rolling year of hourly CAMS data — 8,000+ hours — so every day in the grid is filled.)

---

## 8. Climate Trend Module (the `/climate` page)

| | |
|---|---|
| **What it shows** | 27 years of regional fire + climate history, plus future projections. Six scrollable sections. |
| **Where the data comes from** | Historical fires from BC Wildfire Service; weather from Open-Meteo ERA5; FWI from our own Van Wagner calculation; future projections from the CMIP6 climate-model structure. |
| **How often it updates** | The per-year metrics rebuild nightly. |
| **How trends are computed** | **Theil-Sen** slopes (a method robust to freak years) with **1,000-sample bootstrap** 95% confidence intervals. A trend is only described as real when its confidence interval excludes zero. |
| **Accuracy & honesty** | Temperature, VPD, and fire-weather trends are statistically significant in our data; precipitation and season-length trends are **not**, and the page says so plainly. The **projection sections (4 & 5) use a structurally-correct synthetic placeholder**, not the live CMIP6 download — labelled clearly on the page. Section 5's future fire-weather count is a coarse one-variable extrapolation, also disclosed. |
| **Known limits** | All trends are sensitive to the start year (we begin in 1999, when the fire record begins, and label the span on every chart). |

---

## Quick reference — all sources at a glance

| Layer | Source | Pull cadence | Computed? | Authoritative? |
|---|---|---|---|---|
| Active Fires | BC Wildfire Service (DataBC) | 15 min | No (verbatim) | Yes |
| Hotspots | NASA FIRMS (VIIRS/MODIS) | 30 min | Filtered only | Yes (raw detections) |
| Evacuation | BC Emergency Management | 5 min | No (verbatim) | Yes |
| FWI | Van Wagner calc on Open-Meteo | 30 min | Yes (official equations) | Method is standard |
| Smoke | ECCC RAQDPS-FW + CAMS | 6 h | Joined readout | Yes (official model) |
| Risk Grid | In-house LightGBM model | Daily | Yes (AI) | No — planning aid |
| AQHI (live) | ECCC GeoMet | 1 h | No (verbatim) | Yes |
| AQ forecast | In-house LightGBM quantiles | On request | Yes (AI) | No — forecast |
| Climate trends | ERA5 + fires + Theil-Sen | Nightly | Yes (statistics) | Method is standard |
| Climate projections | CMIP6 (synthetic placeholder) | Nightly | Placeholder | ⚠ not live yet |

---

*Last reviewed: 2026-05-28. For the engineering-level account of every pipeline, see [`logic.md`](./logic.md). For per-field parquet schemas, see [`data-dictionary.md`](./data-dictionary.md).*
