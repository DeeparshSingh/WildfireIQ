# How WildfireIQ works, and how to extend it

This is the one document to read to understand where every number in the
platform comes from, how it moves from a public data source to the screen,
how often it updates, and what to change to cover a new city, region or
province. It assumes no prior knowledge of the code. Every statement here is
taken from the code as it stands; file names are given so anything can be
checked.

Companion documents: [`architecture.md`](./architecture.md) for engineering
detail, [`data-dictionary.md`](./data-dictionary.md) for the exact columns of
every data file, the two [model cards](./model-cards/), and
[`assistant.md`](./assistant.md) for the in-app assistant.

---

## 1. What the platform is

WildfireIQ is a web application for British Columbia with five surfaces:

| Surface | What it shows | Route |
|---|---|---|
| **Globe** | A 3D map with six live layers: active fires, satellite hotspots, evacuation zones, fire-weather stations, the smoke forecast, and an AI risk grid | `/` |
| **Air Quality** | Live AQHI, a 48-hour PM2.5 forecast with uncertainty, a pollutant breakdown, a 365-day smoke calendar, Health Canada guidance | `/air-quality` |
| **Prepare** | A personalised FireSmart checklist, a live "am I in an evacuation zone" check, badges, a private share link | `/preparedness` |
| **Climate** | 27 years of fire-season history for the Thompson-Okanagan, trend statistics, and scenario projections | `/climate` |
| **Assistant** | A question-answering assistant that reads the same data through 25 tools and can move the map | ⌘K on every page |

It runs on one machine, uses public data sources, and stores no personal
information on the server. The assistant is metered per question (fractions of
a cent) against the owner's own OpenRouter key.

Four features need a key from their provider: the globe's terrain and imagery
(Cesium Ion), satellite hotspots (NASA FIRMS), the pollutant breakdown (WAQI)
and the assistant (OpenRouter). Keys are entered once in the app's Settings
panel, the key icon in the top bar. The browser keeps them in local storage and
sends them to the backend, which stores them in `data/runtime/keys.json` (not
tracked by git) so the scheduled jobs and the assistant can use them with no
browser open. Where a key is missing, the feature shows a short notice that
opens Settings; nothing else is affected.

---

## 2. The big picture: how data flows

```
 Public sources ──(timers)──▶ Ingest jobs ──▶ Parquet files ──▶ API ──▶ Browser
 BCWS · EMCR · NASA          17 jobs, each     data/processed/    FastAPI   React + Cesium
 ECCC · Open-Meteo · WAQI    on its own cron   one file per       :8000     :5173
                                               dataset
                                                    │
                                          Two trained models read the
                                          same files at request time
```

Four things to know:

1. **Every dataset is a file.** Each ingest job pulls from one public source
   and writes one Parquet file under `data/processed/`. The API never calls a
   public source while answering a request; it reads the file. This is why the
   app stays fast and keeps working when an upstream service is down — it
   serves the last good file.
2. **Every job runs on its own clock.** Fast-moving feeds (evacuations, fires)
   refresh every few minutes; slow ones (27 years of weather) refresh nightly.
   The full schedule is in §4.
3. **The browser re-checks on its own clock too.** Each map layer and chart
   re-asks the API on an interval matched to how fast that data changes
   (60 seconds for fires and evacuations, 30 minutes for the risk grid).
4. **On startup, anything stale is refreshed first.** When the API starts,
   any dataset whose last successful refresh is older than 30 minutes is
   pulled again immediately, in an order that respects which jobs feed which
   (§4.3). Opening the app after a week away still shows today's data.

---

## 3. Where every number comes from

Coverage tells you the geographic reach of each source as configured today.
"BC" means the whole province (a bounding box in
`apps/api/wildfireiq_api/constants.py`, `BC_BBOX_*`). "Kamloops" means a
single point (`KAMLOOPS_LAT`, `KAMLOOPS_LON` in the same file).

### 3.1 The Globe

| Layer | Source and provider | What is pulled | Refreshed | Coverage | Key |
|---|---|---|---|---|---|
| Active fires | **BC Wildfire Service** via DataBC WFS (`PROT_CURRENT_FIRE_POLYS_SP`, `PROT_CURRENT_FIRE_PNTS_SP`) | Every current incident: name, size, stage of control, perimeter or point | every 15 min | BC | none |
| Satellite hotspots | **NASA FIRMS** near-real-time (VIIRS NOAA-20, VIIRS SNPP, MODIS) | Thermal detections in the last 3 days with radiative power and confidence | every 30 min | BC | NASA FIRMS key, entered in Settings |
| Evacuation zones | **BC Emergency Management and Climate Readiness** ArcGIS FeatureServer | Every order, alert and rescind with its polygon | every 5 min | BC | none |
| Fire-weather stations | **Open-Meteo** daily weather for 18 BC towns, run through Canada's **Van Wagner FWI equations** (`ml/fwi.py`) | weather since 1 April per town → today's FFMC, DMC, DC, ISI, BUI, FWI, DSR | every 6 h | BC, 18 towns | none |
| Smoke forecast | **ECCC FireWork** (RAQDPS-FW) via MSC GeoMet WMS | 73 hourly forecast images, each paired with the predicted PM2.5 at Kamloops | every 6 h | BC | none |
| AI risk grid | The platform's own **wildfire risk model** (§5.1) | Risk class for 523 hexagons across 4 regions | computed on request from data refreshed nightly | 4 regions | none |

The official Fire Weather Index feed from **NRCan CWFIS** is pulled once a day
too (`cwfis_fwi_daily`, 23:00 UTC), into its own file. It is a cross-check, not
a substitute: CWFIS lists only 11 stations inside British Columbia and none of
the 18 towns people search for here, so the in-house calculation is what the app
serves. Where a CWFIS station sits close enough to one of ours to compare, the
two agree on Drought Code to about 1.5%, which is the best evidence available
that `ml/fwi.py` is right.

This job reported "GeoServer unreachable" for the whole build. It was wrong —
NRCan had renamed the WFS layer, and a broad `except` turned that into an
outage. Fixed in the September 2026 audit.

### 3.2 Air Quality

| Item | Source and provider | Refreshed | Coverage | Key |
|---|---|---|---|---|
| AQHI at stations | **ECCC MSC GeoMet**, `aqhi-observations-realtime` | hourly | BC (34 stations reporting) | none |
| Pollutant breakdown (PM2.5, PM10, O3, NO2, SO2, CO) | **WAQI / AQICN** feed nearest Kamloops | hourly | Kamloops | WAQI token, entered in Settings |
| Hourly PM2.5 history and forecast inputs | **Open-Meteo** air-quality API (CAMS), last 7 days + 5 days ahead, with co-located weather | hourly | Kamloops | none |
| Deep archive behind the smoke calendar and the forecaster | Same Open-Meteo API, backfilling the last 365 days | nightly 02:40 UTC | Kamloops | none |
| 48-hour PM2.5 forecast | The platform's own **air-quality model** (§5.2) | computed on request | Kamloops | none |
| Health guidance | **Health Canada** AQHI bands, stored in `data/geo/health_guidance.json` | static | — | none |

### 3.3 Prepare

| Item | Source | Refreshed |
|---|---|---|
| Checklist actions | **FireSmart Canada** Home Ignition Zone guidance, 30 actions curated in `data/firesmart/firesmart_actions.json` | static |
| Neighbourhoods | 14 Kamloops neighbourhood polygons in `data/geo/kamloops_neighbourhoods.geojson` | static |
| "Am I in a zone?" | Point-in-polygon test against the live evacuation file | every 60 s in the browser |
| Days since rain, season peak | Computed on request from the Kamloops daily weather file and the historical fire archive | hourly in the browser |

Everything the user enters — neighbourhood, home type, completed actions,
photos — stays in their browser (`localStorage` and IndexedDB). The server
never receives it.

### 3.4 Climate

| Item | Source | Refreshed |
|---|---|---|
| Fire history | **BC Wildfire Service** historical incidents via DataBC, 1999 to today, province-wide (96,356 records), filtered to the Thompson-Okanagan box for this page | pulled once at setup; re-run to extend |
| Weather history | **Open-Meteo ERA5** reanalysis at Kamloops, 1999 to today, with the last 15 days spliced from the forecast API so the series always reaches today | nightly 02:20 UTC |
| Fire weather history | Van Wagner FWI computed over the full weather history | nightly 02:30 UTC |
| Per-year metrics table | Built from the three above by `ml/seasonal_metrics.py` | nightly 02:30 UTC |
| Trend statistics | **Theil-Sen** median slope with a 1,000-sample bootstrap 95% confidence interval, computed on request | — |
| Scenario projections | **A synthetic placeholder** shaped like a CMIP6 ensemble (SSP1-2.6, SSP2-4.5, SSP5-8.5). The page labels it as such. Replacing it with a real ClimateData.ca download is a file swap. | one-time |
| Fire-danger days by decade | A disclosed heuristic: a straight-line fit of observed high-danger days against July temperature, evaluated at scenario warming | computed on request |

The current year is withheld from the climate page until October so a
half-finished season cannot distort a trend; the API says so in its response.

### 3.5 Assistant

The assistant does not have its own data. Its 25 tools call the same
functions the API uses, and a short **situation brief** (today's risk per
region, fire count, evacuations, air quality, weather) is placed in front of
the model on every question. The model is **GLM 5.3 Flash** from Z.ai,
reached through **OpenRouter**; it is the only paid component, at a measured
$0.0006-$0.0013 per answer across repeated sweeps, and it is rate- and
budget-limited. Details:
[`assistant.md`](./assistant.md).

---

## 4. How and when things update

### 4.1 The schedule

All times are UTC. Each row is one ingest job (`apps/api/wildfireiq_api/ingest/`).

| Every few minutes | | 
|---|---|
| `bcem_evac` | every 5 min |
| `databc_fires_current` | every 15 min |
| `firms_hotspots` | every 30 min |
| `derived_fwi_stations` | every 6 hours |

| Hourly | |
|---|---|
| `open_meteo_kamloops` (current, hourly, daily weather) | :05 |
| `geomet_aqhi_realtime` | :10 |
| `open_meteo_aq_hourly` | :15 |
| `waqi_kamloops` | :25 |

| Every 6 hours | |
|---|---|
| `firework_smoke_forecast` | 00:00, 06:00, 12:00, 18:00 |

| Nightly, in dependency order | |
|---|---|
| `cwfis_fwi_daily` (NRCan's official FWI, as a cross-check) | 23:00 |
| `open_meteo_archive_kamloops` — 27-year ERA5 archive, extended to today | 02:20 |
| `derived_region_weather` — the same for Kelowna, Vancouver, Prince George | 02:25 |
| `derived_seasonal_metrics` — the climate page's per-year table | 02:30 |
| `derived_risk_features` — the risk model's feature table and hexagon weights | 02:35 |
| `open_meteo_aq_archive` — 365-day air-quality archive | 02:40 |

| One-time (run by `./start.sh --bootstrap`) | |
|---|---|
| `databc_fires_historical` — the province-wide fire record since 1999 | re-run yearly to extend |
| `climatedata_projections` — the synthetic projection placeholder | — |

### 4.2 What the browser does

| Data | Browser re-checks |
|---|---|
| Active fires, evacuations, AQHI, evacuation check | every 60 s |
| Satellite hotspots | every 5 min |
| Fire-weather stations, AQ forecast | every 10 min |
| Smoke forecast, risk grid | every 30 min |
| Smoke calendar, season context | every hour |
| Checklist, guidance, climate history | once a day |

Re-checking is cheap: the API answers from a file in milliseconds.

### 4.3 Startup catch-up and dependency order

Some nightly jobs read the output of others: the risk features need every
region's weather archive; the seasonal table needs the Kamloops archive. The
cron times above are staggered for that, but a catch-up at startup has no
clock to lean on. So each job declares what it depends on (`depends_on`), and
the catch-up runs jobs in **waves** — every job in a wave in parallel, the
next wave only after the previous finishes. If a job that is *not* stale
reads the output of one that *is*, it is pulled in too, so a derived file is
never older than its inputs. A dependency typo or cycle stops the API from
starting rather than silently reordering data.

### 4.4 When a source fails

- The job records the failure in a SQLite table (`ingest_runs`), visible at
  `GET /api/admin/runs`, and tries again at its next scheduled time.
- The API keeps serving the last good file. Every response carries the
  source and the time the data was captured, so staleness is visible.
- Transient errors (timeouts, HTTP 5xx) are retried three times with
  back-off before counting as a failure. Rate limits (HTTP 429) on the
  weather archive are waited out with widening delays.
- Raw upstream responses are kept for debugging under `data/raw/<job>/`,
  newest 24 per job, pruned automatically.

### 4.5 Where things live on disk

```
data/
├── processed/    one Parquet file per dataset — what the API and models read
├── raw/          untouched upstream responses, newest 24 per job
├── models/       the two trained models and their metrics
├── geo/          neighbourhood polygons, Health Canada guidance
├── firesmart/    the 30 checklist actions
└── wildfireiq.db SQLite: the ingest_runs log only
```

`processed/` and `raw/` are not committed to git; they are rebuilt from the
public sources. The models are committed so a fresh clone can serve
predictions without retraining.

---

## 5. The two models, briefly

Both are **LightGBM** gradient-boosted tree models trained in seconds on a
laptop. Full detail, metrics and limitations are in the model cards.

### 5.1 Wildfire risk (`wildfire_risk_v1`)

**Question it answers:** what is the probability that at least one fire
ignites somewhere in a region today, given that region's weather?

- **Regions:** Thompson-Okanagan (Kamloops), Central Okanagan (Kelowna),
  Lower Mainland (Vancouver), Prince George. One pooled model for all four,
  with each region's long-run fire rate as a feature so a wet coastal region
  is not scored like the dry Interior.
- **Inputs (42 per region-day):** that region's weather, the six FWI codes,
  7- and 30-day lags and means, drought signals, calendar terms.
- **Labels:** the BC Wildfire Service record — did a fire start in that
  region's box that day?
- **Validation:** trained on 1999–2021, calibrated on 2022, scored on a fully
  unseen 2023. Reported per region so a weak region cannot hide behind the
  average: PR-AUC 0.72 Thompson-Okanagan, 0.61 Prince George, 0.51 Central
  Okanagan, 0.29 Lower Mainland, against a Fire-Weather-Index baseline of 0.37.
- **From region to hexagon:** the region's probability is multiplied by each
  H3 (resolution 5, roughly 250 km²) hexagon's historical fire frequency, then
  bucketed: below 0.05 Low, to 0.20 Moderate, to 0.50 High, above Extreme.
  Within a region the hexagons differ by history, not by separate weather.
- **Next to it, always:** the official CFFDRS fire-danger class from the same
  FWI (Low 0–1, Moderate 2–4, High 5–12, Very High 13–20, Extreme 21+), so the
  AI can be sanity-checked against the standard.

### 5.2 Air quality (`aq_forecaster_v1`)

**Question it answers:** what will PM2.5 be in Kamloops 1, 3, 6, 12, 24, 36
and 48 hours from now, and how sure are we?

- **21 models:** one per horizon × quantile (10th, 50th, 90th). The chart
  shows the median with the 10–90 band as the uncertainty.
- **Inputs:** recent PM2.5 and its lags, co-located weather (temperature,
  humidity, wind, precipitation, boundary-layer height), time of day.
- **Validation:** fitted on the first 70% of a 469-day record, held out on
  the rest. It beats the "tomorrow equals today" baseline at every horizon
  from six hours out, by 6–22%, and loses below that — at one to three hours
  PM2.5 barely changes hour to hour, so repeating the last reading is hard
  to beat.
- **The band is calibrated.** Drawn straight from the 10th and 90th
  percentiles it covered only 59–68% of observations while implying 80%, so
  it is widened by a per-horizon factor measured on data the fit never saw
  (conformalized quantile regression). Measured coverage is now 79–81%
  against a nominal 80%. The factor is recomputed on every retrain, and the
  model card explains what that guarantees and what it does not across a
  change of season.

---

## 6. Extending the platform

The platform is organised so that geography is configuration, not code. This
section says what to change, in order of effort.

### 6.1 What is already province-wide

Fires, hotspots, evacuations, fire-weather stations, AQHI stations and the
smoke overlay already cover all of BC. Their reach is one bounding box:

```python
# apps/api/wildfireiq_api/constants.py
BC_BBOX_WEST, BC_BBOX_SOUTH, BC_BBOX_EAST, BC_BBOX_NORTH = -139.0, 48.3, -114.0, 60.0
```

Widening that box widens every one of those layers at once — **for the
sources that have data there**. Which brings us to the real constraint:

### 6.2 Which sources are BC-only

| Source | Reach | If you leave BC |
|---|---|---|
| BC Wildfire Service (current + historical fires) | BC | Replace with the target province's wildfire agency feed (Alberta Wildfire, Saskatchewan, Ontario AFFES, Yukon Wildland Fire), or the national **CWFIS** active-fire and historical layers from NRCan, which cover all of Canada |
| BC EMCR (evacuations) | BC | Replace with the province's emergency-management feed; there is no national one |
| NASA FIRMS | Global | No change |
| ECCC GeoMet (AQHI, smoke) | Canada | No change |
| Open-Meteo (weather, ERA5, CAMS) | Global | No change |
| NRCan CWFIS (FWI) | Canada | No change |
| WAQI | Global | Change the point |
| FireSmart Canada guidance, Health Canada bands | Canada | No change |

Each source is one file in `apps/api/wildfireiq_api/ingest/`. A replacement
job needs to write the same columns to the same Parquet file
(see `data-dictionary.md`); everything downstream then works unchanged.

### 6.3 Adding a city to the risk model

This is the most common extension and it is designed to be a data change.
The list of modelled regions is one Python list:

```python
# apps/api/wildfireiq_api/constants.py
REGIONS = [
    {
        "key": "thompson_okanagan",
        "label": "Thompson-Okanagan (Kamloops)",
        "lat": 50.6745, "lon": -120.3273,            # anchor city: weather is sampled here
        "bbox": (-121.5, 50.0, -118.5, 51.5),         # west, south, east, north
        "weather_file": "weather_kamloops_archive_daily.parquet",
    },
    ...
]
```

To add, say, Cranbrook:

1. Append an entry with a key, label, anchor coordinates, a bounding box
   that does **not overlap** an existing one, and a new `weather_file` name.
2. `make region-weather` — pulls 27 years of ERA5 weather for the anchor.
3. `make risk-features` — rebuilds the feature table and hexagon weights
   for every region, including the new one.
4. `make train-risk` — retrains the pooled model and writes per-region
   metrics. Check the new region's PR-AUC in
   `data/models/wildfire_risk_v1/metrics.json` and add it to the model card.
5. Restart the API.

Everything else follows automatically: the globe's region selector, the
assistant's place lookup, the "which region is this point in" logic, and the
nightly jobs. Two rules to respect:

- **Hexagons belong to one region.** Where two boxes overlap, the first
  region in the list wins. Keep boxes disjoint.
- **The fire history must cover the box.** Labels come from the BC Wildfire
  Service record, so a region outside BC needs a fire-history source first
  (§6.2). Inside BC nothing else is needed.

### 6.4 Moving the home city

Several things are pinned to Kamloops because it is the platform's home.
To make another city the home, change each:

| What | Where |
|---|---|
| The anchor point for weather, hourly air quality and WAQI | `KAMLOOPS_LAT`, `KAMLOOPS_LON` in `constants.py`; the job names and file names say "kamloops" and would be renamed |
| The climate page's region | `BBOX_*` in `constants.py` (also `REGIONS[0]`) |
| Neighbourhoods for the Prepare page | `data/geo/kamloops_neighbourhoods.geojson` — 14 polygons with a name and a centroid |
| Fire-weather station towns | the `STATIONS` list in `ingest/derived_fwi.py` |
| Place names the assistant understands | the community list in `assistant/gazetteer.py` and its default location |
| Camera presets and on-screen wording | `apps/web/src/features/globe/CameraPresets.tsx`; search the web app for "Kamloops" |

### 6.5 Adding a new data layer

Every existing layer follows one pattern, so a new one is mostly filling in
a template:

1. **Ingest job** — a class in `ingest/` with a `name`, a `cadence` (cron),
   an optional `depends_on`, and a `run()` that fetches, normalises, and
   writes one Parquet file. Register it in `ingest/registry.py`. The runner
   adds retries, logging, raw-snapshot retention and the run log without
   further code.
2. **Reader** — a function in `routers/_data.py` that loads the file.
3. **Endpoint** — a router in `routers/` returning the standard
   `{data, meta}` envelope with source and attribution.
4. **Frontend** — a typed hook in `apps/web/src/lib/api/hooks.ts` and a
   layer or chart component that uses it.
5. **Assistant** — optionally, a tool in `assistant/tools/` so the assistant
   can answer about it.
6. **Tests** — a schema test for the job's output and a router test.

### 6.6 Beyond Canada

The FWI equations, the H3 grid, the ERA5 archive, the CAMS air-quality data,
FIRMS hotspots and the model code are all global. The pieces that are
Canadian are the AQHI (Health Canada's index; other countries use AQI
scales), the FireSmart guidance, and the fire-history and evacuation feeds.
Outside Canada, expect to replace those three and to re-express air quality
in the local index.

### 6.7 Retraining

Retrain the risk model when the fire record gains a year
(`databc_fires_historical`, then `make risk-features`, `make train-risk`).

Retrain the air-quality model any time the archive has grown
(`make train-aq`). Do this at least once a season: the archive keeps
extending, and the run recomputes the band's calibration factor along with
the model. The factor is only as good as the range of conditions the record
covers, so each additional smoke season makes the band more trustworthy.

Both run in under a minute and rewrite their metrics files. Update the model
cards when the numbers change — the cards carry the corpus span they belong
to for exactly this reason.

---

## 7. Keywords

| Term | Meaning here |
|---|---|
| **AQHI** | Air Quality Health Index, Health Canada's 1–10+ scale. Computed from PM2.5 as `(1000/10.4) × (exp(0.000487 × PM2.5) − 1)` |
| **PM2.5** | Particles under 2.5 µm across, the harmful part of smoke, in µg/m³ |
| **FWI** | Fire Weather Index, Canada's fire-danger number, built from FFMC, DMC, DC, ISI and BUI |
| **CFFDRS** | Canadian Forest Fire Danger Rating System; its classes label the FWI |
| **ERA5** | ECMWF's global weather reanalysis, the source of the 27-year weather history |
| **CAMS** | Copernicus atmosphere service, the source of the hourly air-quality history |
| **H3** | Uber's hexagonal grid system; resolution 5 is about 250 km² per cell |
| **Parquet** | A compressed columnar file format; every dataset here is one |
| **PR-AUC** | Area under the precision-recall curve; how well fire days rank above non-fire days, higher is better |
| **Isotonic calibration** | A step function that maps model scores to real frequencies so "0.7" means about 70% |
| **Theil-Sen** | A trend slope robust to extreme years, used on the climate page |
| **SSP** | Shared Socioeconomic Pathway, an emissions scenario (1-2.6 low, 2-4.5 medium, 5-8.5 high) |
| **Ingest job** | One scheduled task that pulls one source and writes one file |
| **Bootstrap** | The one-time pull of historical datasets on first setup |
