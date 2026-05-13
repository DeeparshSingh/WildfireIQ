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

**Phase 4 will add**: time scrubber so users can step through the 48-hour
forecast hour-by-hour.

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

## Phase 4 · Air Quality Monitor (coming next)

Will include the AQHI dial, 48-hour PM2.5 forecast with q10/q50/q90
quantile bands, smoke event calendar, health guidance. The forecaster
needs hourly historical PM2.5 from the BC Air Data Archive — not yet
ingested. Logic for the forecaster will land here when built.

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

---

## Cross-cutting · Refresh cadences

| Layer | Cadence | Hook polling |
|---|---|---|
| Active Fires | 15 min ingest | 60 s frontend |
| Hotspots | 30 min ingest | 5 min frontend |
| Evac | 5 min ingest | 60 s frontend |
| FWI | daily ingest | 10 min frontend |
| Smoke Forecast | 6 h ingest | 30 min frontend |
| AQ realtime | hourly ingest | — (Phase 4) |
| AI Risk Grid | daily inference | 30 min frontend |

---

*Updated through Phase 3. Append new sections as later phases ship.*
