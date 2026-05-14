# Phase 4 — Air Quality Monitor (the second AI model + a dedicated route)

**Status**: ✅ AQ forecaster trained, `/air-quality` route live, all proposal-Phase-4 deliverables shipped.
**Date**: 2026-05-13

## Headline numbers

- **2,208 hourly rows** of pollutant + co-located weather ingested from Open-Meteo CAMS (92 days back, refreshed hourly with +5 day forecast)
- **21 LightGBM quantile models** trained — 7 horizons × 3 quantiles
- **Beats persistence baseline at 6, 12, 36, 48 h** by 0.3-0.9 µg/m³ MAE
- **5 React components** in a full `/air-quality` dashboard

## What was built

### Backend
- `OpenMeteoAQArchiveJob` (one-shot bootstrap, 92 days) + `OpenMeteoAQHourlyJob` (cron `15 * * * *`, rolling 7d + 5d forecast).
- `train_aq.py` — per-horizon, per-quantile LightGBM with co-located weather, lags, and calendar features. Test MAE q50:
  | h | model | persistence |
  |---|---|---|
  | +6 h | 2.27 | 2.85 |
  | +12 h | 3.20 | 4.06 |
  | +48 h | 3.32 | 3.92 |
- `aq_infer.py` — runtime predict + smoke calendar aggregator. Health Canada AQHI conversion from PM2.5.
- `/api/aq/forecast` — issued time + 12 observed h + 7 forecast points each with q10/q50/q90 + aqhi_q50
- `/api/aq/calendar?days=N` — per-day max-PM2.5 / max-AQHI
- `/api/aq/health-guidance` — 4 Health Canada AQHI bands × 3 audiences

### Frontend (`apps/web/src/features/air-quality/`)
- `AqhiDial` — bespoke 320 px SVG arc dial with path-length tween animation, AQHI-band glow when ≥ 7
- `ForecastChart` — Visx area + line chart with q10-q90 cyan band, q50 median, 12-hour observed history, dashed "now" line
- `PollutantBars` — six horizontal bars normalised to CAAQS 24-hour standards
- `SmokeCalendar` — GitHub-style heatmap of daily max-AQHI for the last 90 days
- `HealthGuidance` — Health Canada AQHI bands with General / At-risk / Outdoor-worker audience tabs
- `AirQualityRoute` — composes all five into a scroll-stacked dashboard

### Companion UI polish (asked in the same message)
- **Glass background pills** for the "Layers" and "Camera Presets" section headers (legible on busy imagery now)
- **Camera preset rows shrunk to single-row** so they no longer overlap the Smoke Forecast layer on shorter viewports
- **Removed the (i) info icon** from the main toggle bar — the LayerDetailModal already has the same explanation as a banner under its title

### Documentation
- `logic.md` Phase 4 sections appended (4.1 archive ingest, 4.2 forecaster, 4.3 dashboard)
- Cross-cutting refresh + attribution tables updated

## Verification

| Check | Result |
|---|---|
| AQ archive bootstrap | ✅ 2,208 rows |
| AQ forecaster training | ✅ 21 models, no warnings |
| Test MAE q50 (avg across horizons) | ✅ 2.69 (persistence 3.11) |
| `/api/aq/forecast` | ✅ 12 obs + 7 forecasts |
| `/api/aq/calendar` | ✅ daily PM2.5 + AQHI |
| `/api/aq/health-guidance` | ✅ 4 bands × 3 audiences |
| `pnpm exec tsc -b --noEmit` | ✅ clean |
| All 5 dashboard components render | ✅ |

## Phase 4 follow-ups (same week, after first round of UI feedback)

Four gaps surfaced in user testing — all fixed:

1. **Smoke timestep parsing** — `firework_smoke` was keeping only the endpoints
   of ECCC's ISO-8601 `start/end/period` interval, yielding 2 timesteps. Added
   `_parse_iso8601_duration` + interval expansion. **2 → 73 hourly timesteps.**
2. **`hoursFromNow` label** in the scrubber collapsed all past times to "now".
   Now distinguishes "12 h ago", "2 d ago", "+6 h", "+1 d".
3. **"How this layer works" banner** ate too much modal height — only 2 list
   rows visible. Made it a collapsible header (one-line summary by default;
   click ▾ to expand). List rows now get the modal's full height.
4. **Very High Risk badge** rendered "11–11+" with a bad line wrap. Now
   collapses to "11+" when `aqhi_max===999` and uses `whiteSpace: nowrap`.

## Phase 4 deliverables that were originally deferred — now shipped

5. **AQHI Web Notifications** (`NotifyMe`): threshold slider (4-10), browser
   permission gate, 60-min cooldown. State entirely in `localStorage`. Zero
   backend writes. Zero PII.
6. **AQHI Stations minimap** (`StationsMap`): 300×300 schematic SVG of the 12
   nearest AQHI stations to Kamloops, distance-projected via local
   equirectangular math. Markers sized by AQHI value, coloured by band.
   Concentric range rings.
7. **Smoke calendar extended 90 → 365 days** to match the Phase 4 plan.

Phase 4 is now feature-complete per the implementation plan.

## What's next — Phase 5

Community Preparedness Hub: neighbourhood selector, FireSmart checklist,
evacuation status widget, gamified progress tracking. All local-only (no PII,
no backend writes). Existing `/api/evac/check` already powers point-in-polygon
lookups.
