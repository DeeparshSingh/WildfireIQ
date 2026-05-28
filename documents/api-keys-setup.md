# API keys setup

WildfireIQ runs against free public data sources. Three free signups are required (and one optional) before full functionality is available.

## 1. Cesium Ion (REQUIRED for Phase 0 globe)

**Purpose**: 3D world terrain, OpenStreetMap buildings, Bing aerial imagery (when zoomed in).
**Free tier**: 5 GB asset storage + 15 GB streaming/month + unlimited apps.

1. Go to https://ion.cesium.com/signin/ and create a free account.
2. After signing in, go to **Access Tokens** in the top nav.
3. Copy the **Default Token** (or click *Create token* and give it a name like `wildfireiq-dev`).
4. Add to `.env` at the project root:
   ```
   VITE_CESIUM_ION_TOKEN=eyJhbGci...your token here...
   ```
5. Restart `pnpm dev`. The globe at `/` will replace the setup notice with the Thompson-Okanagan flyover.

If you don't add a token, the app still runs — the globe page just shows a friendly "Add your Cesium Ion token" panel.

## 2. NASA FIRMS (REQUIRED for Phase 1+ satellite hotspots)

**Purpose**: VIIRS / MODIS active fire detections.
**Free tier**: 5,000 transactions per 10-minute window.

1. Visit https://firms.modaps.eosdis.nasa.gov/api/map_key
2. Enter an email — your MAP_KEY arrives instantly.
3. Add to `.env`:
   ```
   FIRMS_MAP_KEY=00000000000000000000000000000000
   ```

## 3. WAQI / AQICN (REQUIRED for Phase 1+ AQ pollutant breakdown)

**Purpose**: Cross-check for Environment Canada AQHI + per-pollutant (PM2.5/PM10/O3/NO2) split.
**Free tier**: ~1,000 req/sec.

1. Visit https://aqicn.org/data-platform/token
2. Fill the short form; the token is emailed within minutes.
3. Add to `.env`:
   ```
   WAQI_TOKEN=your-token-here
   ```

## 4. MapTiler Cloud (OPTIONAL — Phase 4)

**Purpose**: Terrain-RGB tiles for the AQ Monitor's small inset map.
**Free tier**: 100,000 tile requests/month.

1. https://www.maptiler.com/cloud/ → free signup.
2. Add to `.env`:
   ```
   MAPTILER_KEY=your-key
   ```

## 5. Google Earth Engine (OPTIONAL — stretch, Phase 2)

**Purpose**: NDVI vegetation health overlay for the wildfire risk model.
**Free tier**: Generous for non-commercial / research use.

Only sign up if you want the vegetation-health stretch goal. https://earthengine.google.com/signup/

---

After updating `.env`, restart both servers:
```bash
pkill -f vite ; pkill -f uvicorn  # if already running
pnpm dev                           # restart cleanly
```
