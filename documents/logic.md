# WildfireIQ Kamloops — Logic & Data Pipeline Reference

Single source of truth for **how every data layer and prediction works**.
For each feature/layer: data source(s) → pipeline → presentation logic → what
the user is seeing and what they aren't. Updated as new phases ship.

This doc is what you read when someone asks "how does X actually work?"

> **TL;DR**: We are not pretending to be the BC Wildfire Service. Every layer
> here is either (a) a faithful re-render of an authoritative public feed
> (DataBC, ECCC, FIRMS, BCEM), or (b) a model trained on that data, with its
> validation results published transparently. **The platform is informational.
> Authoritative guidance always comes from BC Wildfire Service and BC
> Emergency Management.** That disclaimer is enforced in the UI footer and
> in every risk-cell detail panel.

---

## Foundation

Not a feature layer — the cinematic intro, AppShell, fonts, design tokens,
camera presets, location search, and the 3D Cesium globe itself.

- **Globe imagery**: Bing Maps Aerial with Labels via Cesium Ion asset id 3.
- **Terrain**: Cesium World Terrain (Ion, free tier).
- **Starfield**: Cesium's built-in Tycho-2 catalog (`skyBox`).
- **Camera**: cinematic flyTo on first boot, restored to last view on revisits.

---

## Live data layers

All layers refresh on a TanStack Query interval the layer's logic justifies
(15 min for current fires, 30 min for FIRMS, hourly for AQ, etc.).

---

### Active Fires (BC Wildfire Service)

**What user sees on globe**: Flame-shaped billboards over fire locations; for
fires with mapped perimeters, a translucent ember-orange polygon outline of
the burned area. Click → fire name, status, hectares, discovery date.

**Source**:
- DataBC WFS endpoints:
  - Perimeters: `pub:WHSE_LAND_AND_NATURAL_RESOURCE.PROT_CURRENT_FIRE_POLYS_SP`
  - Points: `pub:WHSE_LAND_AND_NATURAL_RESOURCE.PROT_CURRENT_FIRE_PNTS_SP`
- BBOX = entire province of BC (so we match what BCWS publicly shows).

**Pipeline**:
1. APScheduler hits both layers every 15 minutes.
2. Each feature → normalised row (`fire_id`, `fire_name`, `status`,
   `stage_of_control`, `hectares`, `discovery_date_utc`, `geom_wkt`,
   `geom_kind`).
3. Both layers concatenated into `data/processed/fires_current.parquet`.
4. Backend `/api/fires/current` filters out `status="Out"` by default —
   pass `?include_extinguished=true` for the full set.

**Why our count differs from BCWS sometimes**: BCWS keeps recently-out fires
in their "current" feed for a few days. We drop them by default so the map
isn't crowded with extinguished incidents. Toggle "Include extinguished"
in the AI Risk Grid modal to re-add them.

**What we do not do**: Any modelling, smoothing, or judgement. This is a
verbatim re-render of the BCWS feed.

---

### Satellite Hotspots (NASA FIRMS)

**What user sees**: Coloured dots scaled by Fire Radiative Power (FRP) — pale
yellow for low-energy hotspots, ember-red for high-energy. Each dot represents
a thermal anomaly the satellite saw within the last 72 hours.

**Source**: NASA FIRMS USFS Near-Real-Time API
(`firms.modaps.eosdis.nasa.gov/usfs/api/area/csv/{KEY}/{SOURCE}/{bbox}/3`).
Three satellite sources: VIIRS NOAA-20, VIIRS SNPP, MODIS Terra/Aqua.

**Pipeline**:
1. Job runs every 30 min for each source.
2. Drop confidence < 30 detections.
3. Concat, dedupe on (lat, lon, acq_datetime, source).
4. Persist to `data/processed/firms_hotspots_recent.parquet`.

**Visual encoding logic**:
- Point size = `clamp(6 + frp/10, 6..20)` pixels.
- Colour ramp by FRP: < 5 MW = ember-200 (pale), 5-30 MW = ember-500
  (orange), > 30 MW = ember-700 (deep red).

**What a hotspot ≠ a fire**: FIRMS flags any thermal anomaly — could be a
fire, could be a solar reflection off a metal roof, could be a gas flare.
Confidence < 30 is filtered out (likely false positives). Even at confidence
> 80, ground-truth is "go check it" not "definitely a wildfire."

---

### Evacuation Zones (BC Emergency Management)

**What user sees**: Polygons coloured by status — solid extreme-red for
Evacuation Order, dashed amber for Alert, faint sage for Rescind.

**Source**: BC Emergency Map's ArcGIS FeatureServer (`Evacuation_Orders_and_Alerts/FeatureServer/0`).

**Pipeline**:
1. Job runs every 5 minutes during fire season, hourly off-season.
2. GeoJSON features filtered to BC-wide bbox intersection (Shapely).
3. Each feature's `ORDER_ALERT_STATUS` (Order / Alert / Rescind) is parsed
   as the lifecycle `status`. The underlying `EVENT_TYPE` (Fire / Flood /
   Landslide / Atmospheric River) is stored separately. *Previously the
   parser conflated these two fields — fixed when audit found "Flood" /
   "Landslide" landing in the status column.*
4. Saved to `data/processed/evac_active.parquet` (overwrite — current
   snapshot only).
5. Backend `/api/evac/check?lat=&lon=` does point-in-polygon (Shapely) so
   the preparedness hub can answer "is my address in an evac zone?"

**Visual encoding logic**:
- Order: `--risk-extreme` fill 32% + 2.5 px solid stroke.
- Alert: `--risk-high` fill 22% + 2 px dashed stroke (caution-tape feel).
- Rescind: `--risk-low` fill 12% + 1.5 px stroke.

**Known fragility**: BC Emergency Management has historically moved their
FeatureServer URL between fire seasons. The job has a backup endpoint list
and logs which one it successfully hit.

---

### Fire Weather Index (CWFIS)

**What user sees** (when CWFIS upstream is alive): Billboard circles at FWI
stations across BC, coloured by FWI value (sage / amber / orange / red /
deep red). Hover → station details with all 7 codes (FFMC, DMC, DC, ISI,
BUI, FWI, DSR).

**Source**: Natural Resources Canada CWFIS GeoServer WFS
(`cwfis.cfs.nrcan.gc.ca/geoserver/public/ows`).

**Pipeline**:
1. Job runs daily 18:00 UTC (after CWFIS's noon-LST observation cycle).
2. WFS GetFeature → station table → `fwi_stations_today.parquet`.
3. Append-only history with dedupe on (station_id, observation_date).

**Current status**: CWFIS GeoServer has been returning HTTP 502 throughout
the build window — their server is genuinely down.
**`derived_fwi_stations` job replaces it entirely**: every 30 minutes it
pulls the last 30 days of daily weather (Open-Meteo) for ~18 representative
BC stations (Kamloops, Vernon, Kelowna, Penticton, Salmon Arm, Merritt,
Logan Lake, Cache Creek, 100 Mile House, Williams Lake, Lillooet, Princeton,
Cranbrook, Castlegar, Revelstoke, Prince George, Fort St John, Smithers),
runs the Van Wagner FWI port on each station's chronological series (so
FFMC/DMC/DC carryover codes are valid), and writes the latest day's row
per station to `fwi_stations_today.parquet` using the same schema CWFIS
would have produced. The frontend `/api/fwi/today` route, the Cesium
`FWIStationsLayer`, and the modal `FwiBrowser` all consume this file
unchanged. The original CWFIS job stays scheduled; whenever NRCan recovers
its server, the canonical values overwrite the derived ones for shared
stations.

---

### Air Quality Realtime (ECCC GeoMet + WAQI)

**What user sees** (the `/air-quality` dashboard surfaces the full picture): Stations within
100 km of Kamloops with their current AQHI value 1-10+.

**Source**:
- Primary: ECCC GeoMet `aqhi-observations-realtime` (Health Canada's
  authoritative AQHI).
- Pollutant breakdown: WAQI / AQICN (PM2.5, PM10, O3, NO2, SO2, CO).

**Pipeline**:
1. GeoMet job hourly → 134-146 stations within bbox →
   `aqhi_stations_recent.parquet` (append + dedupe).
2. WAQI job hourly → single Kamloops pollutant row →
   `aq_pollutants_recent.parquet`.

**Why two sources**: ECCC publishes the canonical AQHI value (the
government's official health-risk metric) but doesn't always break out
individual pollutant concentrations. WAQI fills that gap.

---

### Smoke Forecast (ECCC FireWork RAQDPS-FW)

**What user sees**: Translucent PM2.5 plume overlay on the globe.

**Source**: ECCC Meteorological Service of Canada GeoMet WMS, layer
`RAQDPS.Sfc_PM2.5-WildfireSmokePlume` (ECCC renames this between seasons —
our job auto-discovers from GetCapabilities).

**Pipeline**:
1. Job every 6 hours pulls GetCapabilities, finds the latest valid run,
   catalogues the available timesteps + GetMap URLs.
2. Frontend uses the first available timestep as a
   `SingleTileImageryProvider` on the Cesium globe (alpha 0.55).

**Time scrubber**: the Smoke Forecast LayerDetailModal
exposes a range slider + prev/next chips + a scrollable list of every
forecast timestep (~73 hourly steps over 3 days after we fixed the ISO-8601
interval parser to expand `start/end/period` properly). Clicking a
timestep or moving the slider updates `useSmokeStore.timestepIndex`, which
the Cesium `SmokeLayer` reads and reactively swaps the WMS PNG overlay.
Opening the scrubber modal auto-enables the smoke layer.

**PM2.5 readout per timestep**: ECCC's RAQDPS-FW WMS returns mostly-
transparent pixels when PM2.5 is low — which makes the layer look "broken"
to a user who can't see the value being rendered. To fix this without
needing a WMS GetFeatureInfo call (slow + flaky), the
`smoke_forecast_metadata` endpoint joins each smoke timestep to our
existing Open-Meteo CAMS hourly forecast by floor-to-hour on
`time_utc`. Every timestep now carries `pm25_at_kamloops` (µg/m³), which
the modal displays as a colour-graded badge per row (sage < 12 →
amber 12-35 → orange 35-55 → red 55-150 → magenta > 150, matching US-EPA
AQI breakpoints). This makes the layer self-evidently useful even on
"clean air" days.

---

## Globe UI

Layer system architecture only — not new data. The viewer mounts once at
AppShell level, layers gate on `dataGateOpen` (set true after intro
completes), and per-layer filters in `useFiltersStore` drive both the modal
results and what the Cesium layers render.

---

## AI risk grid (the wildfire risk classifier)

**The most consequential layer**, hence the most detailed explanation.

### What user sees
523 H3 r=5 hexagons (~250 km² each) across four modelled regions, each
coloured **Low** (sage), **Moderate** (amber), **High** (orange), or
**Extreme** (red). A selector card in the layer modal turns regions on and
off individually or all at once. Click a hex → P(cell), P(region today),
historical fire count, that region's CFFDRS class, model attribution.

| Region | Anchor city (weather) | Cells |
|---|---|---:|
| Thompson-Okanagan | Kamloops | 185 |
| Prince George (Cariboo) | Prince George | 166 |
| Lower Mainland | Vancouver | 87 |
| Central Okanagan | Kelowna | 85 |

The region list lives in `constants.REGIONS` and is the single source of
truth: the weather job, the feature builder, inference, and the tests all
read it, so adding a fifth region is a config change plus one archive
download.

### What the model is actually predicting
> "What is the probability that **at least one wildfire ignites somewhere
> in this region today**, given that region's weather, its Fire Weather
> Index codes, its recent drought trajectory, and its long-run fire-day
> rate?"

It is **not** a per-cell ignition probability. Each region's probability is
multiplied by each of its H3 cells' sqrt-normalised historical fire-day
count to produce the per-cell display.

### One model, four regions
A single LightGBM classifier is trained on all four regions pooled
together (33,576 region-days), not four separate models. Two reasons:

1. **More evidence for the same physics.** How dryness turns into ignition
   risk is the same relationship everywhere; pooling gives the model four
   times the examples of it. Pooling raised held-out 2023 PR-AUC in the
   Thompson-Okanagan from 0.66 (single-region) to 0.72, so this is not a
   trade of accuracy for coverage.
2. **A base-rate feature keeps regions distinct.** `region_fire_rate` is
   each region's fire-day frequency over 1999-2021 only. Without it the
   model would score wet coastal Vancouver as if it were the dry Interior.
   It computes from training years alone, so no future information leaks
   backwards.

### Why not per-cell weather?
Each region reads its own ERA5 series at its anchor city, but *within* a
region all cells still see the same weather. BC has ~250 weather stations
and BCWS interpolates between them; we don't ingest that station network.
Until we do, per-cell variation inside a region is purely historical fire
density.

### Cells belong to exactly one region
Region bounding boxes touch (Thompson-Okanagan and Central Okanagan share
an edge at 50.0 °N). The feature builder walks `REGIONS` in order and the
first region to claim an H3 cell keeps it, so no hexagon is ever drawn
twice with two different colours. `test_risk_regions.py` asserts zero
duplicates in `cell_density.parquet`.

### The region badge matches the map
A region's headline class is **the highest class covering at least 15% of
its cells** (`risk_infer._region_risk_level`), not the CFFDRS class derived
from its raw FWI. Those two disagree: Vancouver's FWI of 25.6 is above the
CFFDRS Extreme threshold of 21, yet almost all its hexagons render Low or
Moderate because its historical density is small. Deriving the badge from
the rendered cells keeps the card from contradicting the map.

### Honest interpretation
- A cell flagged **Extreme** today means: "this region's fire-day
  probability is high, AND this cell has historically been in the top tier
  of fire-prone places when the region is active."
- A cell flagged **Low** can still burn, especially where there is ample
  fuel but no recent history.
- Within a region, the relative ordering among same-class cells comes from
  historical density, not today's local weather.
- The Lower Mainland is a genuinely low-event area: 35 fire-days in the
  2023 test year against Thompson-Okanagan's 106. That is why it reads Low
  and also why it is the hardest region to score.

### Comparison to BC Wildfire Service's official Fire Danger Rating
BCWS uses the **Canadian Forest Fire Danger Rating System (CFFDRS)** — a
deterministic set of equations Van Wagner & Pickett (1985), parameterised
per weather station. Their daily Fire Danger classes are pinned to FWI:

| FWI value | BCWS Fire Danger class |
|---|---|
| 0-1 | Low |
| 2-4 | Moderate |
| 5-12 | High |
| 13-20 | Very High |
| ≥ 21 | Extreme |

**We surface this CFFDRS class alongside the ML prediction** so users see
both the canonical metric and the model's refinement (see
`risk_infer.py::cffdrs_class_for`). The ML adds value by capturing
non-linear interactions FWI alone misses: on held-out 2023 it beats the
FWI-threshold baseline in three of four regions, by 35 points in the
Thompson-Okanagan.

### Pipeline

1. **Historical fires** (`fires_historical.parquet`): 96,356 BC incidents
   1999-2026 from DataBC bulk WFS, province-wide. Each region filters to
   its own bbox at label time. The download was always province-wide, so
   widening from one region to four cost nothing extra upstream.
2. **Historical weather**: one ERA5 archive per region
   (`weather_{kamloops,kelowna,vancouver,prince_george}_archive_daily.parquet`),
   ~10,100 daily rows each from 1999-01-01, with a spliced 15-day forecast
   tail so today always has a value. ERA5 itself lags about five days.
3. **Derived FWI** (`wildfireiq_api/ml/fwi.py`): Van Wagner equations port,
   run per region. Inputs: temp_max, RH_min, wind_max, precip. Outputs:
   FFMC, DMC, DC, ISI, BUI, FWI, DSR. Carryover values reset Dec-Mar.
4. **Features** (`wildfireiq_api/ml/features.py`): 42 features per
   region-day — current weather, 7 FWI codes, 1d/7d lags, 7d/30d rolls,
   drought signal, calendar (DOY sin/cos, month), and `region_fire_rate`.
   40,368 rows total.
5. **Cell density**: assign every fire an H3 r=5 cell, count per cell,
   sqrt-normalise within its region → weight in [0, 1].
6. **Train** (`wildfireiq_api/ml/train_risk.py`): LightGBM binary,
   train 1999-2021, val 2022, test 2023, all regions pooled. Isotonic
   calibration fitted on val.
7. **Inference** (`wildfireiq_api/ml/risk_infer.py`): per request, predict
   P(fire-day) per region from that region's latest weather state.
   Multiply by each cell's weight. Bucket.

### Held-out 2023 metrics

Reported per region rather than as one pooled average, so pooling cannot
hide a regression in a single area.

| Region | Fire-days | Base rate | PR-AUC | FWI threshold |
|---|---:|---:|---:|---:|
| Thompson-Okanagan | 106 | 0.29 | **0.72** | 0.37 |
| Prince George | 67 | 0.18 | **0.61** | 0.37 |
| Central Okanagan | 64 | 0.18 | **0.51** | 0.37 |
| Lower Mainland | 35 | 0.10 | 0.29 | 0.37 |

Pooled across all four regions: PR-AUC 0.58 raw, ROC-AUC 0.87, Brier
0.108. Climatology baseline 0.19. Note that isotonic calibration lowers
pooled PR-AUC slightly (0.58 → 0.55) while leaving Brier unchanged: it
trades a little ranking sharpness for probabilities that mean what they
say, which is the right trade for a colour scale.

### Top features (by gain importance)
1. DMC (duff moisture, medium-term drying)
2. BUI (buildup index)
3. VPD 7-day mean
4. Reference evapotranspiration (et0)
5. Wind 30-day mean
6. DOY cos (seasonality)
7. `region_fire_rate`
8. Temp 7-day mean
9. VPD 30-day mean
10. RH 7-day mean

Moisture and drying dominate, seasonality follows, and the base-rate term
lands seventh — exactly where it should: informative about which region
you are in, not a shortcut that lets the model ignore the weather.

### Identical probabilities between regions are a calibration artifact

The isotonic calibrator is a step function with 48 output levels, so two
regions whose raw scores land inside one step report the same calibrated
probability exactly. Verified not to be a modelling failure: across the
last 60 days the mean same-day spread between the four regions is 0.53
and they were never all equal, with 60-day means of 0.74 (TO), 0.60
(CO), 0.25 (LM) and 0.22 (PG).

### Bucket thresholds (cell-risk score `p_cell = p_region × weight`)

| p_cell | Class |
|---|---|
| < 0.05 | Low |
| 0.05-0.20 | Moderate |
| 0.20-0.50 | High |
| ≥ 0.50 | Extreme |

These thresholds are not from CFFDRS — they're from the calibration of our
specific model on 2022 val predictions. The CFFDRS-equivalent class is
shown separately in the cell detail panel.

### Limitations (also enumerated in the model card)

1. One weather series per region, not per cell.
2. No NDVI / fuel-state per cell.
3. No lightning data (the dominant natural ignition source).
4. No human-ignition proxy (population, road density, long-weekends).
5. Static historical weights — not climate-change adjusted.
6. Lower Mainland performance is below its own FWI baseline; disclosed in
   the UI and the model card rather than averaged away.

### Anti-uses
- **Do not** use this for evacuation decisions or operational firefighting.
- **Do not** use this for insurance underwriting.
- **Do not** use this as a substitute for BCWS guidance.

---

## Air quality monitor

A dedicated `/air-quality` route plus the proposal's second ML model:
a 48-hour PM2.5 forecaster with quantile uncertainty bands.

### AQ archive ingest (Open-Meteo CAMS)

**Source**: `air-quality-api.open-meteo.com/v1/air-quality` — hourly
pollutant concentrations from CAMS European reanalysis + forecast.
Past_days=92 + forecast_days=5 covers training and prediction in one call.

**Pipeline**:
1. **Bootstrap** (`OpenMeteoAQArchiveJob`, one-shot): 92 days at Kamloops
   centroid → 2,208 hourly rows. Pollutants: PM2.5, PM10, O3, NO2, SO2,
   CO + European AQI. Joined with co-located weather (temp, RH, wind,
   precip, boundary-layer height).
2. **Recurring** (`OpenMeteoAQHourlyJob`, cron `15 * * * *`): 7 days back
   + 5 days forecast, upserted by `time_utc` so the file always covers
   the freshest 12-day window.
3. Output: `data/processed/aq_hourly_kamloops.parquet`.

**Why CAMS, not BC Air Data Archive**: CAMS gives hourly pollutant +
weather in one API call, free, no signup. The BC Archive would give longer
history but requires FTP + per-station joins. CAMS gets a working
forecaster shipping today; the BC Archive can extend history later.

### 48-hour PM2.5 forecaster (`aq_forecaster_v1`)

**Model**: 21 LightGBM quantile regressors — 7 horizons × 3 quantiles.
- Horizons: +1, +3, +6, +12, +24, +36, +48 hours
- Quantiles: 0.10, 0.50, 0.90

**Why per-horizon, not recurrent**: avoids error compounding, trains in
seconds. Uncertainty widens naturally with horizon. **Why quantile, not
point**: smoke events are bimodal (mostly clean / occasionally very bad);
a point forecast hides the risk. The chart shows the q10-q90 band as a
soft uncertainty halo around the q50 median.

**Features per row (21)**:
- PM2.5 current + 5 lags (h-1, h-3, h-6, h-12, h-24) + 6h-mean + 24h-mean
- Co-pollutants: PM10, O3, NO2
- Co-located weather: temp_c, rh_pct, wind_kmh, wind_dir, precip_mm,
  boundary_layer_m
- Calendar: hour_sin, hour_cos, dow_sin, dow_cos

**Target**: PM2.5 (µg/m³) at the chosen horizon.

**Splits**: 80% chronological train (1,766 rows), 20% holdout test.

**Test MAE q50 vs persistence baseline**:

| Horizon | Our model | Persistence | Δ |
|---|---|---|---|
| +1 h | 0.67 | 0.66 | tie |
| +3 h | 1.63 | 1.70 | ↓0.07 |
| +6 h | **2.27** | 2.85 | **↓0.58** |
| +12 h | **3.20** | 4.06 | **↓0.86** |
| +24 h | 3.82 | 3.63 | +0.19 |
| +36 h | **3.90** | 4.19 | ↓0.29 |
| +48 h | **3.32** | 3.92 | **↓0.60** |

Genuinely beats persistence at 6, 12, 36, 48 h. Persistence is hard to
beat at +1 h (yesterday's value is right most of the time) — that's
expected and well-known.

**PM2.5 → AQHI conversion**: standard Health Canada component formula
`AQHI ≈ (1000/10.4) × (exp(0.000487 × PM2.5) − 1)`. This is the PM2.5-only
approximation; real AQHI also uses NO2 + O3, but in wildfire smoke
contexts PM2.5 dominates by an order of magnitude.

**Pipeline files**:
- `wildfireiq_api/ml/train_aq.py` — training script
- `wildfireiq_api/ml/aq_infer.py` — runtime inference + calendar aggregation
- `data/models/aq_forecaster_v1/h{1,3,6,12,24,36,48}/q{10,50,90}.txt` — boosters
- `data/models/aq_forecaster_v1/metrics.json` — per-horizon MAE + pinball

### The `/air-quality` dashboard route

**Components** (all under `apps/web/src/features/air-quality/`):

1. **`AqhiDial`** — 320 px bespoke SVG arc dial. 270° sweep. Filled arc
   animates 0 → current AQHI (path-length tween, 1.4 s). Centre shows
   giant integer AQHI + band label. Glows when AQHI ≥ 7.
2. **`ForecastChart`** — Visx area + line chart, 760 × 280:
   - q10-q90 band: cyan-glow fill
   - q50 median: cyan-glow line
   - Trailing 12 observed h: white line + AQHI-coloured dots
   - Dashed ember "now" line at issue time
3. **`PollutantBars`** — 6 horizontal bars (PM2.5/PM10/O3/NO2/SO2/CO)
   normalised to CAAQS 24-hour standards. Glow when ≥ 66% threshold.
4. **`SmokeCalendar`** — GitHub-style heatmap of daily *max* AQHI for the
   last 365 days. Hover shows date + max PM2.5 + max AQHI.
5. **`HealthGuidance`** — Health Canada AQHI bands with three audience
   tabs (General / At-risk / Outdoor workers). Active band glows. Links
   to BCCDC + Interior Health references.
6. **`StationsMap`** — schematic SVG minimap of the 12 nearest AQHI
   stations to Kamloops, projected via local equirectangular math. Three
   concentric range rings, markers sized by AQHI value, coloured by band.
   Not a real basemap — a purpose-built compact panel that shows *which*
   stations are reporting and how far away. A MapLibre-based version was
   considered and rejected: a full basemap adds a dependency and a tile
   budget for a panel whose only job is to answer "how far away is that
   reading?".
7. **`NotifyMe`** — Web Notification subscription with AQHI threshold
   slider (4-10). Subscription state lives entirely in `localStorage`;
   when current AQHI ≥ threshold and ≥ 60 minutes since last alert, fires
   a native browser notification. **No backend writes, no PII.**
   Permission gated via `Notification.requestPermission()`. Notifications
   fire only while a tab is open — acceptable for the research demo
   (no service worker required, no FCM, no cost).

**Refresh cadences**:
| Source | Frontend re-fetch |
|---|---|
| AQHI stations | 60 s |
| Forecast | 10 min |
| Calendar | 60 min |
| Health guidance | 24 h (static config) |

**Endpoints**:
- `GET /api/aq/current` — current AQHI stations + WAQI pollutant breakdown
- `GET /api/aq/forecast` — 48-h quantile forecast + last 12 observed hours
- `GET /api/aq/calendar?days=365` — per-day max-PM2.5 / max-AQHI series
- `GET /api/aq/health-guidance` — static Health Canada bands

**Attribution**: Open-Meteo CAMS (PM2.5 archive) · ECCC GeoMet (AQHI) ·
WAQI/AQICN (pollutant split) · Health Canada (AQHI bands).

**Limitations**:
- Training window is 92 days. The forecaster generalises well within
  the seasonal regime it was trained on; significant regime shifts
  (e.g., first major smoke event of summer) may degrade accuracy until
  fresh data is ingested.
- PM2.5-only AQHI approximation — see above.
- Forecast is for Kamloops centroid only. Per-neighbourhood AQ forecasting
  would need a station network we do not ingest.

---

## Community preparedness hub

Local-storage + IndexedDB only — no accounts, no PII ever leaves the device.
Lives at `/preparedness`.

**Onboarding (3-step inline wizard)**

1. **Pick your neighbourhood** — typeahead over 14 Kamloops neighbourhoods
   loaded from `/api/firesmart/neighbourhoods` (backed by
   `data/geo/kamloops_neighbourhoods.geojson`). Selecting one captures the
   centroid lat/lon that drives every downstream lookup.
2. **Tell us your situation** — six multi-select chips (house with yard,
   renter, pets, sensitive group, outdoor worker, mobility considerations).
   Optional.
3. **Notification preferences** — AQHI alert threshold slider (4–10) and
   evac-alerts toggle. If toggled on, we request Web Notification
   permission once.

Wizard answers persist to `localStorage` under `wildfireiq.profile.v1`.

**Three-column hub layout (stacks on iPad portrait)**

- **Left — live situational readouts** (`LiveStatusPanel`):
  - Evacuation status for your neighbourhood (60-s refresh)
  - Current Kamloops AQHI from ECCC GeoMet
  - Highest Fire Weather Index among the nearest three stations
  - Days since last 5 mm+ rain in Kamloops
  - Days to the historical fire-season peak — derived as the
    area-weighted median day-of-year of 1999-2025 BC fires (currently
    early July, computed not hardcoded).
- **Centre — the checklist** (`Checklist`):
  - 30 actions sourced from FireSmart Canada's Home Ignition Zone
    workbook, hosted in `data/firesmart/firesmart_actions.json`.
  - Grouped into 5 sections: Immediate (0–1.5 m), Intermediate Inner
    (1.5–10 m), Intermediate Outer (10–30 m), Extended (30–100 m), and
    Plan & Go-Bag.
  - Filtered by **dwelling** + **situation** chips, then **re-ordered**
    by season relevance — each action carries
    `season_priority: {spring, summer, fall, winter}`, so spring puts
    pruning/clearing at the top, summer surfaces go-bag readiness and
    grass cutting, fall prioritises canopy thinning.
  - Each row: title, estimated minutes, cost band, category,
    expandable "why this matters" detail, points chip, photo capture
    button.
  - **Photos** captured via `<input capture="environment">` (native
    iPad/iPhone camera) and stored as blobs in IndexedDB
    (`wildfireiq.progress.v1` / `photos` store). Photos never traverse
    the network and aren't included in shared URLs.
- **Right — progress** (`ProgressPanel`):
  - Score panel: points / max, % complete, animated progress bar,
    streak counter, "N to go" ticker.
  - All 12 achievements always visible (earned = full opacity + amber
    accent; unearned = greyed). Catalogue served by
    `/api/firesmart/achievements`.
  - **Share my progress** — generates a `/preparedness/shared#<base64>`
    URL that encodes the profile + progress in the hash and copies it
    to the clipboard. Recipients land on `SharedView`, which decodes
    the hash entirely client-side (no server hit, no photos).
  - **Reset profile + progress** — wipes localStorage and IndexedDB.

**Achievements (12 total)**

`first_steps` · `ember_aware` · `zone_one_hero` · `defensible_space` ·
`halfway` · `photo_documentarian` · `smoke_aware` · `streak_7` ·
`streak_30` · `storm_ready` (Plan & Go-Bag done before July 1) ·
`neighbour` (shared the link) · `firesmart_home`. Each fires once and
triggers a 1.2 s canvas confetti burst (respects
`prefers-reduced-motion`). Rules live both client-side (for instant
reaction) and in `/api/firesmart/score` so any future surface stays
consistent.

**Streaks**

`rolloverStreak()` runs once per session: if `lastVisitDay === today`
no-op; if `=== yesterday` increment; otherwise reset to 1. Drives the
`streak_7` and `streak_30` badges.

**Web Notifications**

If the user opted in during onboarding, a state-change watcher fires a
notification when evac status transitions to Alert or Order. Rate-
limited by `lastEvacStatus` in progress state so we don't re-notify on
every poll.

**Backend endpoints**

- `GET /api/firesmart/checklist?dwelling=&season=&situation=` — the 30
  curated actions, dwelling-gated, situation-gated, season-ordered.
- `GET /api/firesmart/neighbourhoods` — 14 Kamloops neighbourhood
  polygons.
- `GET /api/firesmart/achievements` — full 12-badge catalogue.
- `GET /api/firesmart/season-context` — `days_since_5mm_rain`,
  `peak_month`, `peak_day`, derived from the Open-Meteo daily wx +
  historical fire parquets at request time.
- `POST /api/firesmart/score` — stateless oracle returning points,
  totals, and the earned-badge list given a completed-ids array, photo
  count, streak, and flags.
- `GET /api/evac/check?lat=&lon=` — Shapely
  point-in-polygon over the live BC EMCR feature collection.

**Privacy contract**

- `localStorage` keys: `wildfireiq.profile.v1`,
  `wildfireiq.progress.v1`. Never transmitted.
- IndexedDB: `wildfireiq.progress.v1` / `photos` store. Photo blobs
  never leave the device.
- Coordinates are sent to `/api/evac/check` purely for polygon lookup,
  never logged with an identifier.
- Share URL encodes only the data the user explicitly chose to share;
  it's a hash fragment so it never reaches our server unless the
  recipient opens the link in this app — and even then we decode it
  client-side.
- No tracking, no analytics, no account.

**Caveats / honest framing**

- The 30-action list is a curated subset of FireSmart Canada's full
  workbook — comprehensive enough to be useful, not a substitute for a
  paid FireSmart Home Partners assessment.
- Neighbourhood polygons are hand-curated bounding boxes around
  centroids derived from City of Kamloops descriptions; not
  survey-accurate, but good enough for "am I near an evac zone?".
- Point weights and the badge ladder are our internal heuristic — they
  reflect FireSmart Canada's impact-per-effort guidance but aren't an
  industry standard.
- Evac check is informational. Follow BC EMCR and BC Wildfire Service
  for official direction.

---

## Climate trend module

A six-section scrollytelling page at `/climate` that tells the story of
how the Thompson-Okanagan's fire seasons have changed and where they're
going. Each section fades in on scroll via `IntersectionObserver`, sits on
a procedural topographic-line backdrop at 4% opacity, and exposes its
source + method + CSV download under an (i) chip.

**Derived dataset — `data/processed/seasonal_metrics.parquet`**

Built by `wildfireiq_api.ml.seasonal_metrics.build()` (run nightly at
02:30 UTC by the `derived_seasonal_metrics` ingest job). One row per year
1999–today, joining:

- Historical fires (`fires_historical.parquet`) aggregated per `fire_year`
  with a bbox filter: total area burned, fire count, largest fire,
  season start/end DOY, season length.
- Open-Meteo ERA5 archive daily wx (`weather_kamloops_archive_daily.parquet`):
  mean July daily-max temperature, July-Aug total precipitation, mean
  July-Aug VPD.
- A fresh Van Wagner FWI run over the entire daily wx archive (using
  `ml/fwi.py`): max July-Aug FWI, count of days with FWI ≥ 19 (the
  CFFDRS extreme threshold).

**Section 1 — "Three decades of fire."** Visx bar chart of annual area
burned (Thompson-Okanagan BBOX). 1999-2010 baseline mean drawn as a
dashed reference line. Five landmark seasons (2003 McLure/Barriere, 2017
Elephant Hill, 2018, 2021 Lytton, 2023) get amber highlight bars +
annotation cards below the chart with the area burned and a one-line
context. The 2003 annotation names McLure/Barriere rather than the
better-known Okanagan Mountain Park fire, because the latter sits at
49.65 °N, south of the Thompson-Okanagan bbox, and so contributes nothing
to the bar being annotated.

**Section 2 — "Hotter, drier air."** Three sparkline panels for mean
July daily-max temp, July-Aug precipitation, July-Aug VPD. Each carries
a Theil-Sen trend line (robust median slope, 1000-bootstrap 95% CI)
plus a slope label like "+4.75 °C since 1999 · CI 0.063 → 0.320
°C/yr". Slope and CI come from `/api/climate/trends`.

**Section 3 — "The shape of a fire season."** One horizontal bar per year
from first-ignition DOY to last-ignition DOY. Bar colour scales with
sqrt(area_burned / max_area), bucketed sage → amber → ember → red. Month
gridlines + a legend below. The title deliberately avoids claiming the
season starts earlier and ends later: the start-DOY trend CI crosses zero
and the end DOY trends *earlier* at −1.32 days/yr, so the section shows
the shape and lets the reader see it.

**Section 4 — "What's coming."** CMIP6 ensemble projections to 2100 under
SSP1-2.6 / SSP2-4.5 / SSP5-8.5. Variable picker (tasmean / tasmax /
pr). Each scenario drawn as a q10–q90 shaded band plus the q50 line,
with a segmented control to toggle scenarios on/off. Observed historical
overlay in off-white. Currently backed by the synthetic CMIP6
placeholder — drop-in replace with the real ensemble is a single
parquet swap (no code change).

**Section 5 — "What this means for fire weather."** Decade-by-decade
projection of `days FWI ≥ 19`. Fits historical `days_fwi_ge_19 ~
mean_july_temp` linearly, evaluates on each scenario's per-decade July
temperature (observed pre-2020; baseline + scaled ΔT thereafter, with
ΔT₂₀₄₀ = 1.0 / 1.8 / 2.9 °C for the three SSPs). Grouped bar chart with
solid (observed) vs. diagonal-stripe (projected) fills. The method
string is explicit about being a coarse heuristic, not a physics run.

**Section 6 — TRU campus carbon (optional).** Renders only when both
`VITE_ENABLE_TRU_CARBON=true` and `data/tru_carbon.csv` exists. Bar
chart of annual tCO₂e with a Sustainability-Office target line.
Otherwise the component returns `null` — the section is fully hidden,
not an empty husk.

**Endpoints**

- `GET /api/climate/seasonal` — full per-year metrics. `?format=csv` for download.
- `GET /api/climate/trends` — Theil-Sen slope + CI for 7 metrics.
- `GET /api/climate/ribbon` — first/last/length DOY + area_burned per year.
- `GET /api/climate/projections-all?var=` — observed + 3 SSPs in one payload.
- `GET /api/climate/projection?ssp=&var=` — single scenario; supports `?format=csv`.
- `GET /api/climate/fwi-projection` — heuristic FWI≥19-days-by-decade with method string + linear-fit coefficients.
- `GET /api/climate/tru-carbon` — feature-flagged; reports `available: false` when the CSV is absent.

**Print stylesheet**

`@media print` strips backgrounds, normalises chart fills, and
`page-break-inside: avoid` on every section — Cmd-P produces a clean
four-page research-artifact PDF.

**Caveats**

- The shipped CMIP6 ensemble is a structurally-correct
  synthetic placeholder, not the real ClimateData.ca download. Section 4
  + 5 trend shapes are illustrative; the slope is wired correctly but
  the absolute values move when the real ensemble is dropped in.
- Section 5's FWI projection is a coarse linear extrapolation of one
  predictor (July temp), explicitly disclosed in the method string.
- All trends are sensitive to the chosen baseline. We start at 1999
  (DataBC's record begins) and document the span in every label.

---

## Engineering polish

- **Frontend**: every non-globe route is code-split behind `React.lazy`;
  the Cesium viewer mounts once at AppShell level and is never remounted.
- **Backend**: `Cache-Control` middleware per endpoint class, DuckDB warmed
  at startup, model and density files held in `lru_cache`.
- **Startup catch-up**: any recurring source older than 30 minutes is
  re-run at boot, in dependency-wave order so a derived job never reads an
  input that is still being rebuilt (`scheduler.refresh_stale_jobs`).
- **Tests**: 77 backend (pytest) and 22 frontend (Vitest), plus ruff lint
  and format checks and a `tsc --noEmit` typecheck, all wired to `make`.

---

## Cross-cutting · Attribution

Every layer renders attribution in the FeatureInfoPanel footer:

| Layer | Attribution |
|---|---|
| Active Fires | BC Wildfire Service · DataBC · Open Government Licence – British Columbia |
| Hotspots | NASA FIRMS · VIIRS / MODIS NRT |
| Evacuation | BC Emergency Management Climate Readiness (EMCR) |
| FWI Stations | Natural Resources Canada · CWFIS |
| Smoke Forecast | ECCC · RAQDPS-FW Wildfire Smoke via MSC GeoMet WMS |
| AQ realtime | ECCC GeoMet · AQHI |
| AQ pollutants | WAQI / AQICN |
| AI Risk Grid | LightGBM, trained on BCWS 1999-2021 + ERA5; validated 2022+2023 |
| AQ Forecaster | LightGBM quantile, trained on Open-Meteo CAMS 92 days; 7 horizons × q10/q50/q90 |

---

## Cross-cutting · Data freshness audit

Every layer's data refresh path. **The APScheduler is enabled by default**
(set `SCHEDULER_ENABLED=false` in `.env` to disable). On every uvicorn
startup, `refresh_stale_jobs()` fires every recurring job whose last
successful run is older than 30 minutes — so cold-start = fresh data
without waiting for the next cron tick.

### Live (refresh continuously while the API is running)

| Layer / endpoint | Upstream source | Ingest cadence | Frontend polling | Notes |
|---|---|---|---|---|
| Active Fires | DataBC WFS `PROT_CURRENT_FIRE_POLYS_SP` + `_PNTS_SP` | every 15 min | every 60 s | BC-wide bbox |
| FIRMS Hotspots | NASA FIRMS USFS NRT CSV (VIIRS NOAA-20, SNPP, MODIS) | every 30 min | every 5 min | last 72 h window |
| Evacuation | BC Emergency Mgmt ArcGIS FeatureServer | every 5 min | every 60 s | order/alert/rescind |
| FWI Stations | Open-Meteo daily weather × 18 BC stations → Van Wagner port | every 30 min | every 10 min | CWFIS GeoServer is down; we run the math ourselves |
| Smoke Forecast | ECCC GeoMet WMS `RAQDPS.Sfc_PM2.5-WildfireSmokePlume` | every 6 h | every 30 min | 73 hourly timesteps |
| Smoke PM2.5 readout | Open-Meteo CAMS PM2.5 hourly forecast (joined into smoke timesteps) | every 60 min | piggybacks smoke fetch | µg/m³ value per timestep |
| AQHI (current) | ECCC GeoMet `aqhi-observations-realtime` | every hour | every 60 s | 134-146 stations near Kamloops |
| AQ pollutant breakdown | WAQI / AQICN `feed/geo:50.67;-120.33` | every hour | every 60 s | PM2.5/PM10/O3/NO2/SO2/CO split |
| Open-Meteo weather (current) | Open-Meteo GEM-HRDPS continental | every hour | every 60 s | for Kamloops centroid |
| Open-Meteo AQ archive | Open-Meteo CAMS (92-day past + 5-day forecast) | every hour, rolling | — (backend reads parquet) | feeds AQ forecaster + smoke joins |

### Inferred at request time

| Endpoint | What it does | Recompute trigger | Frontend polling |
|---|---|---|---|
| `/api/risk/grid` | LightGBM wildfire risk classifier → 523 H3 r=5 cells across four regions | each request (cached via `lru_cache` for model + density file; features re-derived per call from each region's weather archive) | every 30 min |
| `/api/aq/forecast` | LightGBM quantile forecaster → 7 horizons × q10/q50/q90 | each request (model cached; features built from latest `aq_hourly_kamloops.parquet` row) | every 10 min |
| `/api/aq/calendar` | Daily PM2.5/AQHI aggregation | each request (just a groupby over the archive parquet) | every 60 min |
| `/api/evac/check?lat=&lon=` | Point-in-polygon over `evac_active.parquet` | each request | — (on-demand) |

### One-shot bootstrap (historical, run once + refreshed yearly)

| Job | Rows | Notes |
|---|---|---|
| `databc_fires_historical` | 96,356 incidents, province-wide (1999-2026) | Spine of the wildfire risk model. Re-run annually. |
| `open_meteo_archive_kamloops` | ~10,100 daily rows (ERA5 1999-today + 15-day forecast tail) | Re-run nightly via scheduler tick to extend the trail. |
| `derived_region_weather` | ~10,100 daily rows × 3 regions (Kelowna, Vancouver, Prince George) | Same shape as the Kamloops archive; feeds the pooled risk model. |
| `eccc_climate_kamloops` | ECCC bulk CSVs | Same as above. |
| `open_meteo_aq_archive` | 2,208 hourly rows (CAMS 92-day) | Re-run hourly via the recurring CAMS job. |
| `climatedata_projections` | 728 synthetic CMIP6 rows | Static placeholder; a real CMIP6 pull is a drop-in parquet replace. |

### Static (never refresh)

| Resource | What it is |
|---|---|
| `health_guidance.json` | Health Canada AQHI bands × 3 audiences |
| `thompson_okanagan.geojson` | The canonical regional bbox |
| Trained LightGBM models (risk + AQ) | Frozen artifacts in `data/models/`; retrained only when we explicitly re-run the train scripts |
| Cesium Ion terrain + Bing aerial imagery | Streamed at view time from Ion CDN |

### How the user sees the freshness

- Every LayerDetailModal banner shows `Refresh: <cadence>`.
- The CoordinateReadout has a live cyan-pulsing dot to signal the globe is live.
- The bottom of the AQ route shows "Updated {HH:MM} YKA".
- Each detail panel (fire, hotspot, evac, risk) shows the `fetched_at_utc`
  timestamp where the upstream provided it.

### Failure modes & resilience

- **CWFIS GeoServer 502** → `derived_fwi_stations` already runs in parallel
  and writes to the same parquet; the layer never goes empty.
- **BCEM URL shuffled between fire seasons** → job has a backup endpoint list.
- **FIRMS rate limit** → tenacity retries 3 times with exponential backoff.
- **Any upstream timeout** → job logs the failure to `ingest_runs` table; the
  scheduler keeps trying on the next tick; cached parquet is served meanwhile.

---

## Handoff state (current)

Every planned feature is implemented. Notable items finalised during the
polish and audit passes:

- **Always-fresh launch.** On startup the backend refreshes any source
  older than 30 minutes, so fires, hotspots, evac, FWI, smoke, AQHI, the
  weather archive, and the AI risk grid are current within seconds.
- **AI risk grid freshness.** The ERA5 archive job runs daily and splices
  the recent observed tail from the forecast endpoint, so the daily
  weather series reaches today and the risk grid is computed on today's
  weather (previously it could lag ~18 days).
- **Multi-region risk grid.** One pooled LightGBM model scores four regions
  from four ERA5 archives; a `region_fire_rate` prior keeps their base
  rates distinct, and every H3 cell is claimed by exactly one region.
  Pooling raised Thompson-Okanagan held-out 2023 PR-AUC from 0.66 to 0.72.
- **Ordered pipeline.** Jobs declare `depends_on`; the startup catch-up
  runs them in dependency waves so `derived_risk_features` can never read
  a region weather archive that is still being rebuilt.
- **Smoke calendar.** The AQ archive pulls a true rolling 365 days via
  `start_date`/`end_date` (CAMS), so the calendar fills the full year.
- **FWI stations.** The multi-station pull caps concurrency and retries on
  HTTP 429, so all 18 BC stations populate reliably.
- **Province-wide coverage.** Active fires, hotspots, evacuation zones,
  FWI stations, AQHI, and the smoke overlay all cover BC. Historical fires
  are ingested province-wide. The AI risk grid covers four modelled regions
  (Thompson-Okanagan, Central Okanagan, Lower Mainland, Prince George) with
  a per-city selector; the climate-trend module stays Thompson-Okanagan
  only. Within a region the risk model uses one weather signal, which is a
  documented limit.
- **Globe panels.** Active-fire and evacuation lists sort newest-first;
  evac has a "hide past" control that removes rescinded zones from both
  the list and the map.
- **Layer copy** rewritten for a non-technical audience; per-layer
  reference in [`data-layer.md`](./data-layer.md).
- **Frontend** code-splits every non-globe route; the backend sets
  Cache-Control headers and warms DuckDB at startup.

### Remaining (optional, not blocking handoff)

- 90-second demo recording.
- On-device iPad usability testing.
- Swap the synthetic CMIP6 placeholder for the live ClimateData.ca
  ensemble (a parquet drop-in; no code change).

---

*Current as of the September 2026 audit. Documentation index is in the project README.*
