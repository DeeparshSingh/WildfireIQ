# Data dictionary

Every processed parquet under `data/processed/` is documented here. Producer = the ingest job that writes it. Consumer = the routers / ML modules that read it.

> **Convention**: every timestamp column is UTC unless its name ends in `_local`. Every coordinate is WGS-84 decimal degrees. Every area is hectares. Every concentration is µg/m³.

---

## `fires_current.parquet`

Active and recently-closed BC fires from the DataBC live feed.

| Column | Type | Notes |
|---|---|---|
| `fire_id` | str | DataBC `FIRE_NUMBER` |
| `fire_name` | str \| null | local name when assigned |
| `status` | str | "Active", "Under Control", "Being Held", "Out" |
| `stage_of_control` | str \| null | BCWS lifecycle stage |
| `hectares` | float | mapped area; nullable for point-only incidents |
| `discovery_date_utc` | timestamp | first report |
| `latitude` / `longitude` | float | WGS-84 |
| `geom_wkt` | str \| null | polygon WKT when mapped, else null |
| `geom_kind` | str | "polygon" or "point" |
| `fetched_at_utc` | timestamp | when this row was pulled |

**Producer**: `databc_fires_current` (cron `*/15 * * * *`). **Consumer**: `/api/fires/current`.

---

## `fires_historical.parquet`

Bulk historical BC fire incidents, province-wide, 1999–today (96,356 rows). Downloaded for all of BC because the risk model now covers four regions; downstream consumers each re-filter to their own bounding box.

| Column | Type | Notes |
|---|---|---|
| `fire_id` | str | DataBC `FIRE_NUMBER` |
| `fire_year` | int | calendar year of discovery |
| `fire_name` | str \| null | local name |
| `hectares` | float | final mapped or reported area |
| `discovery_date_utc` | timestamp | |
| `ignition_cause` | str \| null | "Lightning", "Person", "Unknown", etc. |
| `latitude` / `longitude` | float | |
| `geom_wkt` | str \| null | |
| `geom_kind` | str | |
| `source_layer` | str | `PROT_HISTORICAL_FIRE_POLYS_SP` or `PROT_HISTORICAL_INCIDENTS_SP` |

**Producer**: `databc_fires_historical` (bootstrap-only). **Consumer**: `/api/fires/historical`, `/api/climate/seasonal`, `ml.train_risk`, `ml.seasonal_metrics`.

---

## `fires_unified.parquet`

Concatenation of `fires_historical` + `fires_current` with dedupe (any fire_id appearing in both keeps the live row). 96,039 rows total.

| Column | Type | Notes |
|---|---|---|
| `fire_id`, `fire_year`, `fire_name`, `hectares`, `discovery_date_utc`, `ignition_cause`, `latitude`, `longitude`, `geom_wkt`, `geom_kind` | as above | union of both feeds |
| `source` | enum | `"historical"` or `"current"` |
| `status`, `stage_of_control` | str \| null | populated only for current rows |

**Producer**: `derived_fires_unified` (cron `15 2 * * *`). **Consumer**: future climate analytics; serves as the single fire source of truth.

---

## `firms_hotspots_recent.parquet`

NASA FIRMS thermal anomalies (VIIRS-NOAA20, VIIRS-SNPP, MODIS) for the last 72 hours.

| Column | Type | Notes |
|---|---|---|
| `latitude` / `longitude` | float | detection centre |
| `acq_datetime_utc` | timestamp | acquisition time |
| `brightness` | float \| null | T4 brightness temp K |
| `frp` | float \| null | Fire Radiative Power MW |
| `confidence` | int \| null | 0–100 (or low/nominal/high for VIIRS, mapped to int) |
| `source` | str | which sensor (e.g. `VIIRS_NOAA20_NRT`) |
| `daynight` | str | `"D"` or `"N"` |
| `satellite` | str | sensor metadata |
| `fetched_at_utc` | timestamp | |

**Producer**: `firms_hotspots` (cron `*/30 * * * *`). **Consumer**: `/api/fires/hotspots`.

---

## `weather_kamloops_current.parquet`

One-row table with the latest Open-Meteo current-conditions for Kamloops.

| Column | Type | Notes |
|---|---|---|
| `time_utc` | timestamp | |
| `temp_c`, `rh_pct`, `wind_kmh`, `wind_dir`, `precip_mm` | float | current values |
| `fetched_at_utc` | timestamp | |

## `weather_kamloops_hourly.parquet`

Open-Meteo 10-day hourly forecast for Kamloops (~240 rows).

## `weather_kamloops_daily.parquet`

Open-Meteo daily forecast (~10 rows ahead) plus the trailing observed days.

| Column | Type | Notes |
|---|---|---|
| `day_local` | date | America/Vancouver |
| `temp_max_c`, `temp_min_c`, `rh_min_pct`, `precip_mm`, `wind_max_kmh`, `wind_gust_max_kmh`, `et0_mm` | float | |
| `is_forecast` | bool | true for future days |

## `weather_kamloops_archive_daily.parquet`

Open-Meteo ERA5 reanalysis archive for Kamloops, **1999-01-01 → today**, with a spliced 15-day forecast tail so the risk model always has a value for today. ~10,100 rows.

| Column | Type | Notes |
|---|---|---|
| `day_local`, `temp_max_c`, `temp_min_c`, `rh_min_pct`, `precip_mm`, `wind_max_kmh`, `wind_gust_max_kmh`, `et0_mm` | as above | |
| `vpd_max_kpa` | float | derived vapour pressure deficit |

**Producer**: `open_meteo_kamloops` + bootstrap `open_meteo_archive_kamloops`. **Consumer**: `/api/weather/*`, `ml.train_risk`, `ml.seasonal_metrics`, `ml.fwi.compute_fwi`.

---

## `weather_{kelowna,vancouver,prince_george}_archive_daily.parquet`

One file per non-Kamloops modelled region, same schema and same date span as
the Kamloops archive above (~10,100 rows each, 1999-01-01 → today). Sampled at
each region's anchor city from `constants.REGIONS`, which is the single source
of truth for the region list. Kamloops keeps its own filename for historical
reasons; the other three follow this pattern.

| Column | Type | Notes |
|---|---|---|
| `day_local`, `temp_max_c`, `temp_min_c`, `rh_min_pct`, `precip_mm`, `wind_max_kmh`, `wind_gust_max_kmh`, `et0_mm`, `vpd_max_kpa` | as `weather_kamloops_archive_daily` | identical schema, so one feature builder handles every region |

**Producer**: `derived_region_weather` (cron `25 2 * * *`). **Consumer**: `ml.features.build_features`, `ml.risk_infer.predict_grid`.

---

## `aqhi_stations_recent.parquet`

ECCC GeoMet AQHI station readings within ~100 km of Kamloops.

| Column | Type | Notes |
|---|---|---|
| `station_id` | str | ECCC identifier |
| `station_name` | str | |
| `latitude` / `longitude` | float | |
| `aqhi` | float | 1–10+ (capped at 12 in raw form) |
| `observation_datetime_utc` | timestamp | |
| `fetched_at_utc` | timestamp | |

**Producer**: `geomet_aqhi_realtime` (cron `*/5 * * * *`). **Consumer**: `/api/aq/current`.

## `aq_pollutants_recent.parquet`

WAQI / AQICN current pollutant readings for Kamloops (PM2.5, PM10, O3, NO2, SO2, CO + dominant pollutant).

## `aq_hourly_kamloops.parquet`

Open-Meteo CAMS hourly air-quality archive co-located with weather features. **The training set for `aq_forecaster_v1`.**

| Column | Type | Notes |
|---|---|---|
| `time_utc` | timestamp | hour beginning |
| `pm2_5`, `pm10`, `co`, `no2`, `so2`, `o3` | float | µg/m³ (or mg/m³ for CO; documented in serving layer) |
| `european_aqi` | float \| null | CAMS-derived |
| `temp_c`, `rh_pct`, `wind_kmh`, `wind_dir`, `precip_mm`, `boundary_layer_m` | float | co-located weather |
| `fetched_at_utc` | timestamp | |

**Producer**: `open_meteo_aq_hourly` (cron `*/60 * * * *`) + bootstrap `open_meteo_aq_archive`. **Consumer**: `/api/aq/forecast`, `ml.train_aq`.

---

## `fwi_stations_today.parquet`

Today's Van Wagner FWI codes for ~18 BC stations. Computed by our own Van Wagner port over 30 days of Open-Meteo daily weather per station (CWFIS GeoServer has been HTTP-502 throughout the build; this replaces it).

| Column | Type | Notes |
|---|---|---|
| `station_id` | str | synthetic id (`open-meteo:{name}`) |
| `station_name` | str | human label |
| `agency` | str \| null | "BCWS / derived" |
| `latitude` / `longitude` | float | |
| `observation_date_local` | date | most recent day |
| `temp_c`, `rh_pct`, `wind_kmh`, `precip_mm` | float | today's inputs |
| `ffmc`, `dmc`, `dc`, `isi`, `bui`, `fwi`, `dsr` | float | full code set |
| `fetched_at_utc` | timestamp | |

**Producer**: `derived_fwi_stations` (cron `*/30 * * * *`). **Consumer**: `/api/fwi/today`.

---

## `smoke_forecast_metadata.parquet`

73 hourly timesteps of the ECCC RAQDPS-FW Wildfire Smoke forecast, joined with the corresponding Open-Meteo CAMS PM2.5 hourly value at Kamloops.

| Column | Type | Notes |
|---|---|---|
| `layer_name` | str | WMS layer id |
| `valid_time_utc` | timestamp | timestep |
| `fetch_url` | str | full WMS GetMap URL ready to embed |
| `pm25_at_kamloops` | float \| null | µg/m³ at the corresponding hour from CAMS |
| `fetched_at_utc` | timestamp | when the WMS GetCapabilities was last read |

**Producer**: `firework_smoke_forecast` (cron `0 */6 * * *`). **Consumer**: `/api/aq/smoke-forecast`, `SmokeLayer`, `LayerDetailModal · SmokeBrowser`.

---

## `evac_active.parquet`

Active BC Emergency Management evacuation orders, alerts, rescinds.

| Column | Type | Notes |
|---|---|---|
| `event_id` | str | BCEM identifier |
| `event_name` | str \| null | local name |
| `status` | str | `Order`, `Alert`, `Rescind`, `Advisory` (`ORDER_ALERT_STATUS`) |
| `event_type` | str | `Fire`, `Flood`, `Landslide` (`EVENT_TYPE`) |
| `issuing_agency` | str | regional district / agency |
| `issued_utc` | timestamp | |
| `area_hectares` | float \| null | polygon area |
| `geom_wkt` | str | polygon WKT |
| `fetched_at_utc` | timestamp | |

**Producer**: `bcem_evac` (cron `*/5 * * * *` in fire season). **Consumer**: `/api/evac/active`, `/api/evac/check`, `EvacLayer`.

---

## `climate_projections.parquet`

CMIP6 ensemble projections — observed + ssp126 / ssp245 / ssp585. **Ships a structurally-correct synthetic placeholder; the real ClimateData.ca pull is a drop-in parquet replace, and the UI says so where it matters.**

| Column | Type | Notes |
|---|---|---|
| `year` | int | |
| `ssp` | str | `"observed"`, `"ssp126"`, `"ssp245"`, `"ssp585"` |
| `variable` | str | `"tasmean"`, `"tasmax"`, `"tasmin"`, `"pr"` |
| `value` | float | central estimate |
| `q10`, `q50`, `q90` | float | ensemble spread |

**Producer**: `climatedata_projections` (bootstrap). **Consumer**: `/api/climate/projection*`, Section 4 of `/climate`.

---

## `seasonal_metrics.parquet`

Per-year joined fire + climate metrics for the Thompson-Okanagan, 1999 → today (27 rows). The headline derived dataset behind the climate-trend module. Scoped to the Thompson-Okanagan even though `fires_historical` is province-wide: this job re-filters by the TO bounding box.

| Column | Type | Notes |
|---|---|---|
| `year` | int | |
| `area_burned_ha`, `fire_count`, `largest_fire_ha` | float / int | from historical fires |
| `season_start_doy`, `season_end_doy`, `season_length_days` | int | DOY of first/last ignition |
| `mean_jul_temp_c` | float | mean of daily max in July |
| `julaug_precip_mm` | float | July + August total precip |
| `mean_julaug_vpd_kpa` | float | mean of daily-max VPD |
| `max_julaug_fwi` | float | peak FWI from Van Wagner |
| `days_fwi_ge_19` | int | count of days at the CFFDRS extreme threshold |

**Producer**: `derived_seasonal_metrics` (cron `30 2 * * *`). **Consumer**: `/api/climate/{seasonal,trends,ribbon,fwi-projection}`, sections 1–5 of `/climate`.

---

## `features_risk_daily.parquet`

Per-region, per-day feature matrix for the wildfire risk classifier. 40,368 rows
(4 regions × ~10,100 days) × 47 columns, of which 42 are model features. Built
by the nightly job and re-used unchanged at serving time, so training and
inference can never disagree about how a feature is computed.

| Column group | Count | Notes |
|---|---:|---|
| `day_local`, `region` | 2 | row key; `region` matches a `constants.REGIONS` key |
| Raw daily weather (`temp_max_c` … `vpd_max_kpa`) | 8 | from that region's own archive |
| Van Wagner FWI codes (`ffmc`, `dmc`, `dc`, `isi`, `bui`, `fwi`, `dsr`) | 7 | computed per region |
| Lags and rolling means (`_lag1`, `_lag7`, `_mean7`, `_mean30`) | 20 | over the five headline weather variables |
| Drought and calendar (`precip_sum7`, `precip_sum30`, `dry_spell_days`, `doy_sin`, `doy_cos`, `month`, `year`) | 7 | |
| `region_fire_rate` | 1 | that region's long-run fire-day rate, computed from 1999–2021 only so no future information leaks backwards |
| `n_fires`, `had_fire` | 2 | labels; `had_fire` is the training target |

**Producer**: `derived_risk_features` (cron `35 2 * * *`). **Consumer**: `ml.train_risk`, `ml.risk_infer.predict_grid`.

---

## `cell_density.parquet`

Historical fire density per H3 r=5 cell, multiplied against its region's
probability to produce the per-cell risk grid. 523 rows: Thompson-Okanagan 185,
Prince George 166, Lower Mainland 87, Central Okanagan 85.

| Column | Type | Notes |
|---|---|---|
| `h3_cell` | str | H3 index (r=5, ~250 km² per cell). Unique across the whole file: where two region bounding boxes overlap, the first region in `REGIONS` claims the cell, so no hexagon is ever drawn twice |
| `region` / `region_label` | str | owning region key and its display name |
| `hist_fire_count` | int | fire-days recorded in this cell, 1999–today |
| `weight` | float | `hist_fire_count` square-root-normalised to 0…1 within its region, so a few extreme cells cannot flatten the rest |
| `region_fire_rate` | float | constant per region; carried here so serving needs only this one file |
| `centroid_lat` / `centroid_lon` | float | cell centre, used to place the hexagon |

**Producer**: `derived_risk_features` (cron `35 2 * * *`). **Consumer**: `ml.risk_infer.predict_grid`, `/api/risk/grid`.

---

## Other reference data (not parquet)

| File | What |
|---|---|
| `data/geo/thompson_okanagan.geojson` | Thompson-Okanagan bbox polygon (the climate module's scope) |
| `data/geo/kamloops_neighbourhoods.geojson` | 14 hand-curated neighbourhood polygons |
| `data/geo/health_guidance.json` | Health Canada AQHI guidance text |
| `data/firesmart/firesmart_actions.json` | 30 curated HIZ checklist actions |
| `data/models/wildfire_risk_v1/{model.txt, calibrator.joblib, metrics.json, features.json, model.onnx}` | risk classifier artifacts |
| `data/models/aq_forecaster_v1/h{H}/q{Q}.txt`, `features.json`, `metrics.json` | 21 quantile boosters |
