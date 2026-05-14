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

## Phase 0 · Foundation

Not a feature layer — the cinematic intro, AppShell, fonts, design tokens,
camera presets, location search, and the 3D Cesium globe itself.

- **Globe imagery**: Bing Maps Aerial with Labels via Cesium Ion asset id 3.
- **Terrain**: Cesium World Terrain (Ion, free tier).
- **Starfield**: Cesium's built-in Tycho-2 catalog (`skyBox`).
- **Camera**: cinematic flyTo on first boot, restored to last view on revisits.

---

## Phase 1 · Live data layers

All layers refresh on a TanStack Query interval the layer's logic justifies
(15 min for current fires, 30 min for FIRMS, hourly for AQ, etc.).

---

### 1.1 · Active Fires (BC Wildfire Service)

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

### 1.2 · Satellite Hotspots (NASA FIRMS)

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

### 1.3 · Evacuation Zones (BC Emergency Management)

**What user sees**: Polygons coloured by status — solid extreme-red for
Evacuation Order, dashed amber for Alert, faint sage for Rescind.

**Source**: BC Emergency Map's ArcGIS FeatureServer (`Evacuation_Orders_and_Alerts/FeatureServer/0`).

**Pipeline**:
1. Job runs every 5 minutes during fire season, hourly off-season.
2. GeoJSON features filtered to bbox intersection (Shapely).
3. Saved to `data/processed/evac_active.parquet` (overwrite — current
   snapshot only).
4. Backend `/api/evac/check?lat=&lon=` does point-in-polygon (Shapely) so
   the Phase 5 preparedness hub can answer "is my address in an evac zone?"

**Visual encoding logic**:
- Order: `--risk-extreme` fill 32% + 2.5 px solid stroke.
- Alert: `--risk-high` fill 22% + 2 px dashed stroke (caution-tape feel).
- Rescind: `--risk-low` fill 12% + 1.5 px stroke.

**Known fragility**: BC Emergency Management has historically moved their
FeatureServer URL between fire seasons. The job has a backup endpoint list
and logs which one it successfully hit.

---

### 1.4 · Fire Weather Index (CWFIS)

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
the build window — their server is genuinely down. The job retries
automatically and will populate when they recover. **Phase 3 made this
non-blocking** by computing FWI ourselves from Open-Meteo weather data
(see § 3.1).

---

### 1.5 · Air Quality Realtime (ECCC GeoMet + WAQI)

**What user sees** (Phase 4 surfaces the full dashboard): Stations within
100 km of Kamloops with their current AQHI value 1-10+.

**Source**:
- Primary: ECCC GeoMet `aqhi-observations-realtime` (Health Canada's
  authoritative AQHI).
- Pollutant breakdown: WAQI / AQICN (PM2.5, PM10, O3, NO2, SO2, CO).

**Pipeline**:
1. GeoMet job hourly → 134-146 stations within bbox →
   `aqhi_kamloops_recent.parquet` (append + dedupe).
2. WAQI job hourly → single Kamloops pollutant row →
   `aq_pollutants_recent.parquet`.

**Why two sources**: ECCC publishes the canonical AQHI value (the
government's official health-risk metric) but doesn't always break out
individual pollutant concentrations. WAQI fills that gap.

---

### 1.6 · Smoke Forecast (ECCC FireWork RAQDPS-FW)

**What user sees**: Translucent PM2.5 plume overlay on the globe.

**Source**: ECCC Meteorological Service of Canada GeoMet WMS, layer
`RAQDPS.Sfc_PM2.5-WildfireSmokePlume` (ECCC renames this between seasons —
our job auto-discovers from GetCapabilities).

**Pipeline**:
1. Job every 6 hours pulls GetCapabilities, finds the latest valid run,
   catalogues the available timesteps + GetMap URLs.
2. Frontend uses the first available timestep as a
   `SingleTileImageryProvider` on the Cesium globe (alpha 0.55).

**Time scrubber** (built in Phase 4): the Smoke Forecast LayerDetailModal
exposes a range slider + prev/next chips + a list view of every available
forecast timestep (typically 13 timesteps over 39 hours). Clicking a
timestep or moving the slider updates `useSmokeStore.timestepIndex`, which
the Cesium `SmokeLayer` reads and reactively swaps the WMS PNG overlay.
Opening the scrubber modal auto-enables the smoke layer so changes are
visible immediately.

---

## Phase 2 · Globe UI

Layer system architecture only — not new data. The viewer mounts once at
AppShell level, layers gate on `dataGateOpen` (set true after intro
completes), and per-layer filters in `useFiltersStore` drive both the modal
results and what the Cesium layers render.

---

## Phase 3 · AI Risk Grid (the wildfire risk classifier)

**The most consequential layer**, hence the most detailed explanation.

### What user sees
185 H3 r=5 hexagons (~250 km² each) covering the Thompson-Okanagan, each
coloured **Low** (sage), **Moderate** (amber), **High** (orange), or
**Extreme** (red). Click a hex → P(cell), P(region today), historical
fire count, model attribution.

### What the model is actually predicting
> "What is the probability that **at least one wildfire ignites somewhere
> in the Thompson-Okanagan region today**, given today's weather, today's
> Fire Weather Index codes, and the recent drought trajectory?"

It is **not** a per-cell ignition probability. That regional probability
is multiplied by each H3 cell's sqrt-normalised historical fire-day count
to produce the per-cell display.

### Why not per-cell weather?
We only have one weather time-series (Kamloops, Open-Meteo ERA5 archive).
BC has ~250 weather stations and BCWS interpolates between them. We don't
yet ingest that station network. Until we do, all cells see the same
weather → per-cell variation is purely historical fire density.

### Honest interpretation
- A cell flagged **Extreme** today means: "regional fire-day probability
  is high, AND this cell has historically been in the top tier of
  fire-prone places when the region is active."
- A cell flagged **Low** can still burn. Especially in cells with no
  recent history but ample fuel.
- All cells flagged "Extreme" on a given day are at roughly the same
  hazard rank; the relative ordering among them comes from historical
  density, not today's local weather.

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
`risk_infer.py::cffdrs_class_for`). The ML adds value (PR-AUC 0.66 vs
FWI-threshold 0.52 → +14.8 points on held-out 2023) by capturing
non-linear interactions FWI alone misses.

### Pipeline

1. **Historical fires** (`fires_historical.parquet`): 15,996 BC incidents
   1999-2025 from DataBC bulk WFS. Restricted to Thompson-Okanagan bbox
   at label time.
2. **Historical weather** (`weather_kamloops_archive_daily.parquet`): 9,992
   daily rows from Open-Meteo ERA5 archive at Kamloops centroid.
3. **Derived FWI** (`wildfireiq_api/ml/fwi.py`): Van Wagner equations port.
   Inputs: temp_max, RH_min, wind_max, precip. Outputs: FFMC, DMC, DC,
   ISI, BUI, FWI, DSR. Carryover values reset Dec-Mar (winter pattern).
4. **Features** (`wildfireiq_api/ml/features.py`): 40 features per day —
   current weather, 7 FWI codes, 1d/7d lags, 7d/30d rolls, drought
   signal, calendar (DOY sin/cos, month).
5. **Cell density**: For each fire 1999-2025, assign H3 r=5 cell. Count
   per cell → sqrt-normalise → weight in [0, 1].
6. **Train** (`wildfireiq_api/ml/train_risk.py`): LightGBM binary,
   train 1999-2021, val 2022, test 2023. Isotonic calibration on val.
7. **Inference** (`wildfireiq_api/ml/risk_infer.py`): Per request, predict
   P(fire-day) using yesterday's weather state. Multiply by each cell's
   weight. Bucket.

### Held-out 2023 metrics

| | Our model | FWI threshold | Climatology |
|---|---|---|---|
| PR-AUC | **0.663** | 0.515 | 0.290 |
| ROC-AUC | **0.870** | — | — |
| Brier | **0.136** | — | — |

### Top features (by gain importance)
1. FFMC (fine fuel moisture)
2. DC (drought code, long-term drying)
3. DMC (duff moisture)
4. FWI (composite)
5. dry_spell_days
6. VPD max
7. temp_max_c
8. BUI
9. DOY cos (seasonality)
10. precip_sum30

Exactly the wildfire-science textbook ranking — good sanity check.

### Bucket thresholds (Phase 3 cell-risk score `p_cell = p_region × weight`)

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

1. Single Kamloops weather station for the whole region.
2. No NDVI / fuel-state per cell.
3. No lightning data (the dominant natural ignition source).
4. No human-ignition proxy (population, road density, long-weekends).
5. Static historical weights — not climate-change adjusted.

### Anti-uses
- **Do not** use this for evacuation decisions or operational firefighting.
- **Do not** use this for insurance underwriting.
- **Do not** use this as a substitute for BCWS guidance.

---

## Phase 4 · Air Quality Monitor

A dedicated `/air-quality` route plus the proposal's second ML model:
a 48-hour PM2.5 forecaster with quantile uncertainty bands.

### 4.1 · AQ archive ingest (Open-Meteo CAMS)

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

### 4.2 · 48-hour PM2.5 forecaster (`aq_forecaster_v1`)

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

### 4.3 · `/air-quality` dashboard route

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
   stations are reporting and how far away. (MapLibre-based version may
   land in Phase 7 polish if needed.)
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
- Forecast is for Kamloops centroid only. Multi-point AQ forecasting
  (per neighbourhood) deferred to Phase 5+.

---

## Phase 5 · Community Preparedness Hub (planned)

Local-storage only (no PII, no backend writes). Neighbourhood selector,
FireSmart checklist composed from canonical FireSmart Canada Home
Ignition Zone actions filtered by user's situation. Points + achievements
gamification. Live evac status via existing `/api/evac/check`.

---

## Phase 6 · Climate Trend (planned)

30-year fire-season severity chart from `fires_historical.parquet`. CMIP6
ensemble projections from ClimateData.ca (currently placeholder synthetic
data). Theil-Sen trend lines with bootstrap CIs.

---

## Phase 7 · Polish (planned)

Performance, accessibility, OSS release, demo recording.

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

## Cross-cutting · Refresh cadences

| Layer | Cadence | Hook polling |
|---|---|---|
| Active Fires | 15 min ingest | 60 s frontend |
| Hotspots | 30 min ingest | 5 min frontend |
| Evac | 5 min ingest | 60 s frontend |
| FWI | daily ingest | 10 min frontend |
| Smoke Forecast | 6 h ingest | 30 min frontend |
| AQ realtime | hourly ingest | 60 s frontend |
| AQ archive (CAMS) | hourly + 92d bootstrap | — |
| AQ forecaster | per-request (cached LightGBM) | 10 min frontend |
| Smoke calendar | derived from CAMS | 60 min frontend |
| AI Risk Grid | daily inference | 30 min frontend |

---

*Updated through Phase 3. Append new sections as later phases ship.*
