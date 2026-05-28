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

Bulk historical BC fire incidents 1999–today (15,996 rows).

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

Concatenation of `fires_historical` + `fires_current` with dedupe (any fire_id appearing in both keeps the live row). 16,091 rows total.

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

Open-Meteo ERA5 reanalysis archive for Kamloops, **1999-01-01 → today**. 9,992 rows.

| Column | Type | Notes |
|---|---|---|
| `day_local`, `temp_max_c`, `temp_min_c`, `rh_min_pct`, `precip_mm`, `wind_max_kmh`, `wind_gust_max_kmh`, `et0_mm` | as above | |
| `vpd_max_kpa` | float | derived vapour pressure deficit |

**Producer**: `open_meteo_kamloops` + bootstrap `open_meteo_archive_kamloops`. **Consumer**: `/api/weather/*`, `ml.train_risk`, `ml.seasonal_metrics`, `ml.fwi.compute_fwi`.

---

## `aqhi_kamloops_recent.parquet`

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

CMIP6 ensemble projections — observed + ssp126 / ssp245 / ssp585. **Phase 1 ships a structurally-correct synthetic placeholder; the real ClimateData.ca pull is a drop-in parquet replace.**

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

Per-year joined fire + climate metrics for the Thompson-Okanagan, 1999 → today (27 rows). The headline derived dataset for Phase 6.

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

Per-day, per-cell feature matrix for the wildfire risk classifier. Built during training and re-used at serving time.

(Schema documented in `apps/api/wildfireiq_api/ml/features.py`.)

## `cell_density.parquet`

Historical fire-day density per H3 r=5 cell — multiplied against the regional probability to produce the per-cell risk grid.

| Column | Type | Notes |
|---|---|---|
| `h3_cell` | str | H3 index (r=5) |
| `density` | float | sqrt-normalised fire-day count |
| `centroid_lat` / `centroid_lon` | float | |

---

## Other reference data (not parquet)

| File | What |
|---|---|
| `data/geo/thompson_okanagan.geojson` | TO bbox polygon |
| `data/geo/kamloops_neighbourhoods.geojson` | 14 hand-curated neighbourhood polygons |
| `data/geo/health_guidance.json` | Health Canada AQHI guidance text |
| `data/firesmart/firesmart_actions.json` | 30 curated HIZ checklist actions |
| `data/models/wildfire_risk_v1/{model.txt, calibrator.joblib, metrics.json, features.json, model.onnx}` | risk classifier artifacts |
| `data/models/aq_forecaster_v1/h{H}/q{Q}.txt`, `features.json`, `metrics.json` | 21 quantile boosters |
