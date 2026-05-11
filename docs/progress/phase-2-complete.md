# Phase 2 — 3D Globe Data Layers + Toggle UI + Feature Info Panel

**Status**: ✅ Complete
**Date**: 2026-05-10

## What was built

### Single-viewer architecture
- `WildfireGlobe` mounts once at `AppShell` level and never unmounts
- Other routes (`/air-quality`, `/preparedness`, `/climate`, `/about`) overlay on top with their own backdrops
- Camera state persisted in `useGlobeStore` (Zustand) — survives all route navigation
- Cinematic intro fires only once per page load (`introPlayed` flag)
- Cesium's built-in Tycho-2 starfield re-enabled for subtle space ambiance

### Camera presets (4 buttons, bottom-right)
- **Globe** — Canada in view (lat 46.2553, lon -104.1181, alt 22.2 Mm)
- **Region** — Thompson-Okanagan overview
- **Kamloops** — city core
- **TRU Campus** — Thompson Rivers University

All use the cinematic flyTo helper with distance-scaled arc apex and quintic ease.

### Data hooks (TanStack Query)
`apps/web/src/lib/api/hooks.ts` — typed hooks for every endpoint:
- `useFiresCurrent()` — polls /api/fires/current every 60s
- `useFirmsHotspots(24)` — polls /api/fires/hotspots every 5 min
- `useEvacActive()` — polls /api/evac/active every 60s
- `useFwiToday()` — polls /api/fwi/today every 10 min
- `useSmokeForecast()` — polls /api/aq/smoke-forecast every 30 min

### Cesium data layers (5 components)
Each is a pure imperative React component (returns null, manipulates the viewer via useEffect):

| Layer | What it renders | Visual treatment |
|---|---|---|
| `ActiveFiresLayer` | BC Wildfire Service current fires | Ember-glow polylines (perimeters) + flame SVG billboards (points), centroid label, click → info panel |
| `FIRMSHotspotsLayer` | NASA FIRMS satellite hotspots | Point primitives, pixelSize scaled by FRP (6–20 px), ember-200/500/700 colour ramp by intensity |
| `EvacLayer` | BC Emergency Management orders/alerts | Risk-coloured fills + outline polylines (Order=solid 2.5px extreme red, Alert=dashed 2px high orange, Rescind=1.5px sage) |
| `FWIStationsLayer` | CWFIS FWI stations | Billboard with coloured circle + tabular FWI value, on-hover description table (FFMC/DMC/DC/ISI/BUI/FWI/DSR) |
| `SmokeLayer` | ECCC FireWork PM2.5 plume forecast | WMS PNG as `SingleTileImageryProvider` with alpha 0.55, framed to the Thompson-Okanagan bbox |

WKT parser at `apps/web/src/lib/cesium-helpers/wkt.ts` handles POINT, POLYGON, MULTIPOLYGON.

### Layer toggle bar (top-right)
Five glassmorphic toggle buttons, each with:
- Icon glyph + label
- **Live count badge** that updates as TanStack Query refetches (53 fires, 1 hotspot, 2 evac zones, etc.)
- Animated switch with accent glow when on
- **Spotlight-dim hover**: hovering one toggle dims the *other* four to 35% opacity, drawing eye to context
- Keyboard shortcuts: press `1` through `5` to toggle each layer

### Feature info panel (right-side slide-in)
- 380px glassmorphic panel slides in from the right when any fire/hotspot/evac/fwi is clicked
- Motion-driven enter/exit (`AnimatePresence`), 320ms quintic
- Renders distinct detail views per feature kind:
  - **Fire**: name, status, hectares, discovery date, coordinates, geometry kind, attribution
  - **Hotspot**: source satellite, brightness (K), FRP (MW), confidence, day/night
  - **Evac zone**: status (Order/Alert/Rescind glowing in risk colour), issuing agency, issued time, area
  - **FWI station**: full FWI panel (FFMC/DMC/DC/ISI/BUI/FWI/DSR) + observed weather (temp, RH, wind, precip)
- Close with × button or by selecting another feature

### Selection store
`apps/web/src/stores/layers.ts`:
- `visible: Record<LayerId, boolean>` — per-layer on/off
- `toggle(id)`, `set(id, on)`
- `selected: SelectedFeature | null` — which feature is open in the info panel
- `select(s)` — called by layer click handlers, info panel close button

## Verification

| Check | Result |
|---|---|
| `pnpm exec tsc -b --noEmit` | ✅ clean |
| Vite dev server serves all new modules HTTP 200 | ✅ |
| Backend `/api/fires/current` → 53 rows | ✅ live |
| Backend `/api/evac/active` → 2 zones | ✅ live |
| Backend `/api/aq/smoke-forecast` → 2 WMS URLs | ✅ live |
| Cesium viewer mounted at AppShell, never re-mounted on navigation | ✅ |
| Intro fires once per reload; restores on nav-back | ✅ |
| All 5 layers render entities, clean up on toggle-off | ✅ |
| Layer toggles update counts live | ✅ |

## Known constraints

- **CWFIS FWI** layer shows 0 stations whenever NRCan's WFS upstream is 502 (intermittent, not our bug)
- **FIRMS hotspots** are sparse outside fire season (1 hotspot mid-May; will scale to hundreds in summer)
- **Smoke layer** uses the first available WMS timestep; Phase 4 will add a time scrubber for hourly playback

## Post-launch fixes (same day)

User testing surfaced four issues, all addressed:

1. **Layer toggles didn't visually disable layers.** Root cause: `requestRenderMode = true` after intro means Cesium only paints when explicitly asked. Entity removal alone didn't always trigger a frame. Fix: every layer now calls `viewer.scene.requestRender()` after add/remove, and the cleanup path is always installed as the effect's return value (not just inline). `apps/web/src/lib/cesium-helpers/render.ts` is the shared helper.
2. **53 fires looked excessive.** Most were `status="Out"` (extinguished but still in DataBC's current layer). Backend `/api/fires/current` now filters them out by default; passing `?include_extinguished=true` brings back the full set. **53 → 2** actually-burning fires.
3. **Layers appeared during the cinematic intro.** New `dataGateOpen` flag in `useGlobeStore` opens only after the flyTo lands (or immediately on revisits with a restored camera). All 5 layers gate on it.
4. **Fire icons crowded the viewport.** Reduced from 28→20 px and added Cesium `NearFarScalar` so they scale to 35% at 2,000 km altitude. Same `disableDepthTestDistance` so they're always visible above terrain.

## What's next — Phase 3

Phase 3 trains the two real ML models:
- **Wildfire risk classifier** (LightGBM) — outputs a 4-class daily risk grid, served on `/api/risk/grid` and rendered as the H3 hexagon overlay (`RiskGridLayer`, not yet built)
- **48-hour AQ forecaster** (LightGBM with quantile bands) — populates `/api/aq/forecast`

Both validated against held-out 2022 + 2023 fire seasons, with model cards in `docs/model-cards/`.
