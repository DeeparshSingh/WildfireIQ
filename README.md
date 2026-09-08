# WildfireIQ Kamloops

Wildfire risk, air quality, climate trends and community preparedness for
British Columbia, on one open platform built entirely from free public data —
with an in-app assistant that answers only from the platform's own data.

Built at Thompson Rivers University under a Sustainability Research Grant
(2025–2026). MIT licensed.

---

## What it does

| Surface | What you get |
|---|---|
| **Globe** (`/`) | A 3D map of BC with six live layers: active fires, satellite hotspots, evacuation orders and alerts, fire-weather stations, an hourly smoke forecast, and an AI wildfire-risk grid of 523 hexagons across four regions |
| **Air Quality** (`/air-quality`) | Live AQHI, a 48-hour PM2.5 forecast with an uncertainty band, a six-pollutant breakdown, a 365-day smoke calendar, and Health Canada guidance |
| **Prepare** (`/preparedness`) | A FireSmart checklist tailored to your home and season, a live "am I in an evacuation zone" check, progress badges, and a share link — all stored in your browser, never on a server |
| **Climate** (`/climate`) | 27 years of Thompson-Okanagan fire-season history with robust trend statistics, plus scenario projections |
| **Assistant** (⌘K, every page) | Ask a question in plain language; it reads the same live data through 25 tools, cites what it used, and can fly the map or switch on a layer |

Two models are trained in the repository and validated on held-out seasons:
a pooled multi-region **wildfire-risk classifier** (LightGBM; held-out 2023
PR-AUC 0.72 for the Thompson-Okanagan against a 0.37 Fire-Weather-Index
baseline) and a **48-hour PM2.5 forecaster** (21 LightGBM quantile models).
Both are documented in [model cards](documents/model-cards/).

---

## Quick start

**Prerequisites:** Node.js 20+, [pnpm](https://pnpm.io), and
[uv](https://docs.astral.sh/uv/) for Python. macOS or Linux.

```bash
git clone https://github.com/DeeparshSingh/WildfireIQ.git
cd WildfireIQ
./start.sh
```

`start.sh` installs dependencies on first run, creates `.env` from
`.env.example`, pulls the historical datasets if they are missing (about ten
minutes, once), and starts both halves. Open **http://localhost:5173**. The
API is at http://localhost:8000 with interactive docs at `/docs`.

### Keys

Three free sign-ups; the app runs without them but with less on screen.

| Variable | Needed for | Get one |
|---|---|---|
| `VITE_CESIUM_ION_TOKEN` | Terrain and imagery on the globe (without it, a setup notice is shown) | https://ion.cesium.com |
| `FIRMS_MAP_KEY` | Satellite hotspots | https://firms.modaps.eosdis.nasa.gov/api/map_key |
| `WAQI_TOKEN` | Pollutant breakdown | https://aqicn.org/data-platform/token |
| `OPENROUTER_API_KEY` | The assistant (optional; the launcher hides without it) | https://openrouter.ai/keys |

Put them in `.env` and restart. Every setting is listed with its default in
[`documents/architecture.md`](documents/architecture.md#6-configuration).

---

## How it works

Seventeen scheduled jobs pull from public sources — the BC Wildfire Service,
BC Emergency Management, NASA FIRMS, Environment and Climate Change Canada,
Open-Meteo and WAQI — on cadences from five minutes to nightly, and write one
Parquet file per dataset. The API serves from those files, so it answers in
milliseconds and keeps working when a source is down. On startup anything
stale is refreshed first, in dependency order. The browser re-checks each
layer on an interval matched to how fast that data changes.

The full account — every source, every cadence, how the models work, and
**how to extend the platform to new cities or provinces** — is in
[`documents/how-it-works.md`](documents/how-it-works.md).

---

## Repository

```
apps/api/        FastAPI backend: 17 ingest jobs, two models, REST API, assistant
apps/web/        React + TypeScript + CesiumJS frontend
packages/        Shared design tokens (CSS variables, fonts)
data/            Parquet datasets (rebuilt from sources), trained models, reference files
documents/       Documentation, model cards, report, abstract
scripts/         One-time bootstrap of historical data
start.sh         Launch everything
Makefile         Every documented command
```

### Commands

```bash
./start.sh                # run both halves (or: make dev, pnpm dev)
./start.sh --bootstrap    # also pull historical datasets first

make test                 # backend tests (158)
cd apps/web && pnpm test  # frontend tests (36)
make lint                 # ruff check + format check
make typecheck            # tsc --noEmit
make build                # production build of the web app

make ingest-all           # run every recurring ingest job once
make train-risk           # retrain the wildfire-risk model
make train-aq             # retrain the air-quality forecaster
make region-weather       # rebuild the per-region weather archives
make risk-features        # rebuild the risk feature table and hexagon weights
make seasonal-metrics     # rebuild the climate page's per-year table
make prune-raw            # trim raw upstream snapshots to retention
make assistant-smoke      # one live assistant call
make assistant-eval       # 32-case live evaluation of the assistant (~$0.04)
```

---

## API

Every response is `{ "data": …, "meta": { "source", "attribution", "note", "cached_at" } }`.
Interactive documentation at `/docs`.

| Group | Endpoints |
|---|---|
| Fires | `/api/fires/current`, `/api/fires/hotspots`, `/api/fires/historical` |
| Risk | `/api/risk/grid`, `/api/risk/today?cell=` |
| Air quality | `/api/aq/current`, `/api/aq/forecast`, `/api/aq/calendar`, `/api/aq/history`, `/api/aq/smoke-forecast`, `/api/aq/health-guidance` |
| Weather / FWI | `/api/weather/current`, `/api/weather/forecast`, `/api/fwi/today` |
| Evacuation | `/api/evac/active`, `/api/evac/check?lat=&lon=` |
| Preparedness | `/api/firesmart/checklist`, `/achievements`, `/neighbourhoods`, `/season-context`, `POST /score` |
| Climate | `/api/climate/seasonal`, `/trends`, `/ribbon`, `/projection`, `/projections-all`, `/fwi-projection`, `/tru-carbon` (`?format=csv` on `seasonal` and `ribbon`) |
| Assistant | `POST /api/assistant/chat` (SSE), `/api/assistant/tools`, `/brief`, `/health` |
| Operations | `/healthz`, `/api/admin/jobs`, `/api/admin/runs`, `POST /api/admin/jobs/{name}/run` |

---

## Documentation

| Document | Read it for |
|---|---|
| [`how-it-works.md`](documents/how-it-works.md) | Where every number comes from, how and when it updates, and how to extend to new regions — start here |
| [`architecture.md`](documents/architecture.md) | Engineering reference: request path, ingest framework, scheduling, models, frontend, configuration, testing |
| [`data-dictionary.md`](documents/data-dictionary.md) | Every column of every data file, with writer and readers |
| [`assistant.md`](documents/assistant.md) | The assistant's harness, tools, grounding rules, limits and cost |
| [`model-cards/`](documents/model-cards/) | Intended use, training, validation and limitations of both models |
| [`WildfireIQ-Abstract.pdf`](documents/WildfireIQ-Abstract.pdf) | Research abstract of the completed platform (also `.docx`) |
| [`WildfireIQ-Report.tex`](documents/WildfireIQ-Report.tex) | The project report, LaTeX source |
| [`project_timeline.tex`](documents/project_timeline.tex), `WildfireIQ_Proposal.pdf` | The funded proposal and its timeline, kept for the record |

---

## Data sources

All free. Attribution is shown in the app beside the data it applies to;
licences are in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

| Source | Data |
|---|---|
| BC Wildfire Service (DataBC) | Current and historical fires |
| BC Emergency Management and Climate Readiness | Evacuation orders, alerts, rescinds |
| NASA FIRMS | Satellite hotspots (VIIRS, MODIS) |
| Environment and Climate Change Canada (MSC GeoMet) | AQHI stations, FireWork smoke forecast |
| Natural Resources Canada (CWFIS) | Fire Weather Index stations, when reachable |
| Open-Meteo | Weather, ERA5 reanalysis, CAMS air quality |
| WAQI / AQICN | Pollutant breakdown |
| FireSmart Canada, Health Canada | Checklist actions, AQHI health guidance |
| Cesium Ion | Terrain and imagery |

---

## Known limitations

- **The platform is informational.** It does not replace the BC Wildfire
  Service, BC Emergency Management or Environment Canada, and says so on
  every surface.
- **One weather series per region.** Hexagons within a region differ by fire
  history, not by separate local weather. The Lower Mainland is a low-event
  area and the hardest region to score; its 2023 PR-AUC (0.29) is below the
  FWI baseline and is disclosed rather than averaged away.
- **The air-quality forecast is for one point** (Kamloops) and cannot see a
  plume arriving from outside until local readings rise.
- **The climate projections are a labelled placeholder** shaped like a CMIP6
  ensemble; the live download is a file swap.
- **The assistant is a language model.** Its tool results are trustworthy;
  its prose about them is not proof, so every answer shows its sources. It is
  rate- and budget-limited rather than authenticated.

---

## Contributing, citing, licence

Contributions are welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md). To cite
the software, see [`CITATION.cff`](CITATION.cff). Code is MIT licensed
([`LICENSE`](LICENSE)); written content is CC BY 4.0.

Created by Deeparsh Singh Dang at Thompson Rivers University with support from
the TRU Sustainability Office.
