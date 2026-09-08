# Data dictionary

Every file under `data/processed/` and `data/models/`, with its columns, the
job that writes it and the code that reads it. Column lists were taken from
the files themselves on 2026-09-08; row counts are from that day and move.

Conventions: a column ending `_utc` is a UTC timestamp, stored as text in
ISO-8601 unless noted; `_local` means America/Vancouver. Coordinates are WGS-84
decimal degrees. Areas are hectares. Concentrations are µg/m³.

"Readers" names the API endpoints and modules that open the file. The
assistant's tools read through the same `routers/_data.py` functions as the
endpoints, so they are not listed separately.

---

## Live feeds

### `fires_current.parquet` — 1,654 rows
Current BC Wildfire Service incidents, province-wide.

| Column | Type | Notes |
|---|---|---|
| `fire_id` | str | DataBC fire number |
| `fire_name` | str | may be empty |
| `status` | str | e.g. Active, Being Held, Under Control, Out |
| `stage_of_control` | str | BCWS lifecycle stage |
| `hectares` | float | mapped area; missing for point-only incidents |
| `discovery_date_utc` | str | |
| `latitude`, `longitude` | float | |
| `geom_wkt` | str | polygon WKT when a perimeter is mapped, else empty |
| `geom_kind` | str | `polygon` or `point` |
| `fetched_at_utc` | str | |

Writer `databc_fires_current` (every 15 min). Readers `/api/fires/current`, the assistant brief.

### `firms_hotspots_recent.parquet` — 27 rows
NASA FIRMS thermal detections in the last 3 days, province-wide.

| Column | Type | Notes |
|---|---|---|
| `latitude`, `longitude` | float | detection centre |
| `acq_datetime_utc` | str | acquisition time |
| `brightness` | float | brightness temperature, K |
| `frp` | float | fire radiative power, MW |
| `confidence` | float | 0–100; VIIRS low/nominal/high mapped to numbers |
| `source` | str | `VIIRS_NOAA20_NRT`, `VIIRS_SNPP_NRT`, `MODIS_NRT` |
| `daynight` | str | `D` or `N` |
| `satellite` | str | |
| `fetched_at_utc` | str | |

Writer `firms_hotspots` (every 30 min). Reader `/api/fires/hotspots`.

### `evac_active.parquet` — 40 rows
BC EMCR evacuation orders, alerts and rescinds, province-wide.

| Column | Type | Notes |
|---|---|---|
| `event_id` | str | |
| `event_name`, `order_alert_name` | str | |
| `event_type` | str | hazard: Fire, Flood, Landslide … |
| `status` | str | lifecycle: Order, Alert or Rescind |
| `issuing_agency` | str | regional district or First Nation |
| `issued_utc` | str | |
| `area_hectares` | float | |
| `geom_wkt` | str | polygon WKT |
| `fetched_at_utc` | str | |

Writer `bcem_evac` (every 5 min). Readers `/api/evac/active`, `/api/evac/check`, the assistant brief.

### `fwi_stations_today.parquet` — 18 rows
Today's Fire Weather Index codes at 18 BC towns.

| Column | Type | Notes |
|---|---|---|
| `station_id`, `station_name`, `agency` | str | |
| `latitude`, `longitude` | float | |
| `observation_date_local` | str | |
| `temp_c`, `rh_pct`, `wind_kmh`, `precip_mm` | float | the day's inputs |
| `ffmc`, `dmc`, `dc`, `isi`, `bui`, `fwi`, `dsr` | float | the full code set |
| `fetched_at_utc` | str | |

Writers `derived_fwi_stations` (every 30 min, Van Wagner over Open-Meteo) and `cwfis_fwi_daily` (daily; the official feed, currently failing upstream). Same schema, same file. Reader `/api/fwi/today`.

### `smoke_forecast_metadata.parquet` — 73 rows
One row per hourly step of the ECCC FireWork smoke forecast.

| Column | Type | Notes |
|---|---|---|
| `layer_name` | str | WMS layer id |
| `valid_time_utc` | str | forecast hour |
| `fetch_url` | str | a complete WMS GetMap URL the globe loads directly |
| `fetched_at_utc` | str | |

Writer `firework_smoke_forecast` (every 6 h). Reader `/api/aq/smoke-forecast`, which joins `pm25_at_kamloops` from `aq_hourly_kamloops` at serve time.

### `aqhi_stations_recent.parquet` — 1,169 rows
Recent AQHI readings at every reporting BC station (several readings each; the API keeps the latest per station).

| Column | Type | Notes |
|---|---|---|
| `station_id`, `station_name` | str | |
| `latitude`, `longitude` | float | |
| `aqhi` | float | 1–10+ |
| `observation_datetime_utc` | str | |
| `fetched_at_utc` | str | |

Writer `geomet_aqhi_realtime` (hourly). Readers `/api/aq/current`, `/api/aq/history`.

### `aq_pollutants_recent.parquet` — 140 rows
WAQI pollutant readings at the station nearest Kamloops; the API serves the newest row.

| Column | Type | Notes |
|---|---|---|
| `station_name` | str | |
| `station_lat`, `station_lon` | float | |
| `aqi` | int | WAQI's own index |
| `pm25`, `o3`, `no2`, `so2` | float | |
| `pm10`, `co` | str | arrive as text from the upstream and are passed through |
| `dominant_pollutant` | str | |
| `observation_time_utc`, `fetched_at_utc` | str | |

Writer `waqi_kamloops` (hourly). Reader `/api/aq/current`.

### `weather_kamloops_current.parquet` — 1 row

| Column | Type |
|---|---|
| `temp_c`, `wind_kmh`, `wind_gust_kmh`, `precip_mm`, `vpd_kpa` | float |
| `rh_pct`, `wind_dir_deg` | int |
| `observed_at_local`, `fetched_at_utc` | str |

### `weather_kamloops_hourly.parquet` — 288 rows
Hourly weather, recent past and forecast.

| Column | Type | Notes |
|---|---|---|
| `ts_local`, `ts_utc` | str | |
| `temp_c`, `rh_pct`, `wind_kmh`, `wind_gust_kmh`, `wind_dir_deg`, `precip_mm`, `vpd_kpa`, `et0_mm` | float | |
| `is_forecast` | bool | |

### `weather_kamloops_daily.parquet` — 12 rows
Daily summary, recent past and forecast. Trailing forecast days beyond Open-Meteo's horizon are all-null and are dropped by the reader.

| Column | Type | Notes |
|---|---|---|
| `day_local` | str | |
| `temp_max_c`, `temp_min_c`, `rh_min_pct`, `precip_mm`, `wind_max_kmh`, `wind_gust_max_kmh`, `et0_mm` | float | |
| `is_forecast` | bool | |

Writer of the three weather files above: `open_meteo_kamloops` (hourly). Readers `/api/weather/*`, `/api/firesmart/season-context` (daily, for days since rain), the assistant brief.

### `aq_hourly_kamloops.parquet` — 11,256 rows
Hourly CAMS air quality with co-located weather at Kamloops; the training set and the live input of the air-quality model, and the source of the smoke calendar.

| Column | Type | Notes |
|---|---|---|
| `time_utc` | timestamp (UTC) | hour beginning |
| `pm2_5`, `pm10`, `co`, `no2`, `so2`, `o3` | float | |
| `european_aqi` | float | CAMS' own index |
| `temp_c`, `rh_pct`, `wind_kmh`, `wind_dir`, `precip_mm`, `boundary_layer_m` | float | co-located weather |
| `fetched_at_utc` | str | |

Writers `open_meteo_aq_hourly` (hourly, 7 days back + 5 forward, upsert on `time_utc`) and `open_meteo_aq_archive` (nightly, 365 days). Readers `/api/aq/forecast`, `/api/aq/calendar`, `/api/aq/smoke-forecast`, `ml.train_aq`.

---

## History and derived tables

### `fires_historical.parquet` — 96,356 rows
Every BC Wildfire Service incident since 1999, province-wide. The spine of the risk model and the climate page.

| Column | Type | Notes |
|---|---|---|
| `fire_id` | str | |
| `fire_year` | int | |
| `fire_name` | str | |
| `hectares` | float | |
| `discovery_date_utc` | str | |
| `ignition_cause` | str | Lightning, Person, Unknown … |
| `latitude`, `longitude` | float | |
| `geom_wkt`, `geom_kind` | str | |
| `source_layer` | str | which DataBC layer the row came from |

Writer `databc_fires_historical` (one-time; re-run to extend). Readers `/api/fires/historical`, `ml.features`, `ml.seasonal_metrics`, `/api/firesmart/season-context` (season peak).

### `weather_kamloops_archive_daily.parquet` — 10,109 rows
Daily ERA5 weather at Kamloops, 1999-01-01 to today, the last 15 days spliced from the forecast API.

| Column | Type |
|---|---|
| `day_local` | str |
| `temp_max_c`, `temp_min_c`, `precip_mm`, `wind_max_kmh`, `wind_gust_max_kmh`, `et0_mm`, `vpd_max_kpa` | float |
| `rh_min_pct` | int |

Writer `open_meteo_archive_kamloops` (nightly 02:20). Readers `ml.features`, `ml.risk_infer`, `ml.seasonal_metrics`, `ingest.climatedata_projections` (as the observed baseline).

### `weather_{kelowna,vancouver,prince_george}_archive_daily.parquet` — 10,109 rows each
Identical schema to the Kamloops archive, one file per other modelled region, sampled at the anchor city in `constants.REGIONS`.

Writer `derived_region_weather` (nightly 02:25). Readers `ml.features`, `ml.risk_infer`.

### `seasonal_metrics.parquet` — 27 rows
One row per complete fire season, 1999 onward, for the Thompson-Okanagan box. The current year is excluded until October.

| Column | Type | Notes |
|---|---|---|
| `year` | int | |
| `area_burned_ha`, `fire_count`, `largest_fire_ha` | float | from the fire archive |
| `season_start_doy`, `season_end_doy`, `season_length_days` | float | day-of-year of first and last ignition |
| `mean_jul_temp_c` | float | mean daily maximum |
| `julaug_precip_mm` | float | July + August total |
| `mean_julaug_vpd_kpa` | float | mean daily-maximum vapour-pressure deficit |
| `max_julaug_fwi` | float | from the Van Wagner run over the archive |
| `days_fwi_ge_19` | int | days at or above the high-danger threshold used on the climate page |

Writer `derived_seasonal_metrics` (nightly 02:30). Readers `/api/climate/seasonal`, `/api/climate/trends`, `/api/climate/ribbon`, `/api/climate/fwi-projection`.

### `features_risk_daily.parquet` — 40,436 rows (grows by 4 a day)
The risk model's training table: one row per region per day, 47 columns of which 42 are model features.

| Group | Columns |
|---|---|
| Key | `day_local` (timestamp), `region` |
| Raw weather (8) | `temp_max_c`, `temp_min_c`, `rh_min_pct`, `precip_mm`, `wind_max_kmh`, `wind_gust_max_kmh`, `et0_mm`, `vpd_max_kpa` |
| FWI codes (7) | `ffmc`, `dmc`, `dc`, `isi`, `bui`, `fwi`, `dsr` |
| Lags and means (20) | `_lag1`, `_lag7`, `_mean7`, `_mean30` for `temp_max_c`, `rh_min_pct`, `wind_max_kmh`, `precip_mm`, `vpd_max_kpa` |
| Drought and calendar (7) | `precip_sum7`, `precip_sum30`, `dry_spell_days`, `doy_sin`, `doy_cos`, `month`, `year` |
| Base rate (1) | `region_fire_rate` — that region's fire-day frequency over 1999–2021 only, so nothing from the validation or test years leaks into training |
| Labels (2) | `n_fires`, `had_fire` (the target) |

Writer `derived_risk_features` (nightly 02:35) via `ml.features.build`. Reader `ml.train_risk`.

### `cell_density.parquet` — 523 rows
One row per H3 resolution-5 hexagon; the weight that turns a region probability into a per-cell score.

| Column | Type | Notes |
|---|---|---|
| `h3_cell` | str | unique across the file; where two region boxes overlap, the first region in `REGIONS` keeps the cell |
| `region`, `region_label` | str | |
| `hist_fire_count` | int | fires recorded in the cell since 1999 |
| `weight` | float | `sqrt(hist_fire_count / max in region)`, 0–1 |
| `region_fire_rate` | float | copied here so inference needs only this file and the weather |
| `centroid_lat`, `centroid_lon` | float | |

Cells per region: Thompson-Okanagan 185, Prince George 166, Lower Mainland 87, Central Okanagan 85.

Writer `derived_risk_features`. Reader `ml.risk_infer` (`/api/risk/grid`, `/api/risk/today`).

### `climate_projections.parquet` — 728 rows
**Synthetic placeholder** shaped like a CMIP6 ensemble, extrapolated from the observed Kamloops archive. The climate page labels it as such. Dropping in a real ClimateData.ca download with these columns needs no code change.

| Column | Type | Notes |
|---|---|---|
| `year` | int | |
| `ssp` | str | `observed`, `ssp126`, `ssp245`, `ssp585` |
| `variable` | str | `tasmean`, `tasmax`, `tasmin`, `pr` |
| `value`, `q10`, `q50`, `q90` | float | |

Writer `climatedata_projections` (one-time). Readers `/api/climate/projection`, `/api/climate/projections-all`.

---

## Models (`data/models/`, committed)

| Path | What |
|---|---|
| `wildfire_risk_v1/model.txt` | LightGBM booster |
| `wildfire_risk_v1/calibrator.joblib` | isotonic calibrator fitted on 2022 |
| `wildfire_risk_v1/features.json` | the 42 feature names, in order |
| `wildfire_risk_v1/metrics.json` | held-out 2023 metrics, per region and pooled |
| `aq_forecaster_v1/h{1,3,6,12,24,36,48}/q{10,50,90}.txt` | 21 LightGBM quantile boosters |
| `aq_forecaster_v1/features.json`, `metrics.json` | feature names; per-horizon pinball loss, MAE and the persistence baseline |

## Reference data (committed)

| Path | What |
|---|---|
| `data/geo/kamloops_neighbourhoods.geojson` | 14 neighbourhood polygons with centroids |
| `data/geo/health_guidance.json` | Health Canada AQHI bands for three audiences |
| `data/firesmart/firesmart_actions.json` | 30 checklist actions in 5 groups, with season priorities |

## Operational

| Path | What |
|---|---|
| `data/wildfireiq.db` | SQLite. One table, `ingest_runs`: one row per job run with status, row counts, duration and any error. Read by `/api/admin/runs`, the startup catch-up, and the assistant's data-freshness tool |
| `data/raw/<job>/` | the last 24 raw upstream responses per job, for reproducing a parse failure |
