# Phase 0 — Foundation, Design System, Monorepo Scaffold

**Status**: ✅ Complete
**Date**: 2026-05-09
**Build mode**: Claude Code, Sonnet 4.6

## What was built

- **Monorepo** at the project root with pnpm workspaces (`apps/*`, `packages/*`) and uv for Python.
- **Frontend** (`apps/web`): React 18 + TypeScript + Vite 5 + Tailwind v4 + Resium + Cesium 1.141 + Motion + TanStack Query + Zustand.
- **Backend** (`apps/api`): FastAPI 0.115 + Python 3.12 + uv + structlog + 8 stub routers covering the entire Phase 1+ API surface.
- **Design tokens package** (`packages/design-tokens`): tactical-dark palette, ember + AQHI + risk-grade colour scales, glassmorphism presets, motion tokens, typography pairing (Bricolage Grotesque + Geist + JetBrains Mono — all self-hosted), grain texture overlay.
- **Shared types** (`packages/shared-types`): TypeScript types auto-generated from the live OpenAPI schema (826 lines, 16 routes typed).
- **AppShell**: persistent left rail (5 routes) + top bar (live UTC + Kamloops clock + phase badge) over a glass / dark backdrop.
- **Splash**: Motion-driven 1.4s logo reveal with reduced-motion fallback.
- **Router**: 5 routes — `/` (Cesium globe smoke test), `/air-quality`, `/preparedness`, `/climate`, `/about`. The four feature routes show distinctive "Coming in Phase N" placeholder cards in the locked design language.
- **Cesium globe smoke test**: full Resium `<Viewer>` with Cesium World Terrain, EOX Sentinel-2 cloudless imagery, atmospheric tuning (hue/saturation/brightness shifts, fog, no sun/moon), tactical baseColor, render-on-demand, FXAA, cinematic 3-second flyTo to the Thompson-Okanagan from a far view.
- **Setup notice**: when no Cesium Ion token is in `.env`, the globe page replaces itself with a glassmorphic "Add your token" panel — production-grade graceful degradation.

## Files

- 17 frontend `.ts/.tsx` files + 1 vite config + 1 tsconfig + 1 biome config + index.html + 3 design-token CSS files.
- 14 backend Python files (main, settings, constants, 8 routers, envelope helper, package init, tests dir).
- 3 self-hosted variable fonts (~860 KB total) + 1 grain texture (64 KB) + favicon SVG.

## Verification

| Check | Result |
|---|---|
| `pnpm install` | ✅ 4 workspace packages, 391 deps, 7s |
| `uv sync` | ✅ FastAPI + dependencies installed |
| `pnpm exec tsc -b --noEmit` | ✅ TYPECHECK OK |
| Vite dev server cold boot | ✅ Ready in 369ms, no warnings |
| `curl http://localhost:5173/` | ✅ HTTP 200, no Google Fonts in HTML |
| `curl http://localhost:5173/fonts/*` | ✅ Self-hosted, HTTP 200 |
| `curl http://localhost:5173/textures/grain.png` | ✅ HTTP 200, 64 KB |
| Vite transforms `WildfireGlobe.tsx` | ✅ HTTP 200 (Cesium imports resolve) |
| `curl http://localhost:8000/healthz` | ✅ `{"ok":true,"version":"0.1.0","phase":"0",...}` |
| `curl http://localhost:8000/openapi.json` | ✅ 17 routes registered |
| Sample router stub | ✅ Returns locked `{data, meta}` envelope |
| `openapi-typescript` codegen | ✅ 826 typed lines |
| `pnpm exec vite build` (production) | ✅ Built in 5.13s |
| Production JS gzipped (excluding Cesium) | ✅ 49 KB (target: ≤ 220 KB at Phase 7) |

## Decisions made during execution

- **Cesium 1.141 + Resium 1.21**: Resium 1.21 expects Cesium 1.123+ APIs (`BufferPoint*`). Bumped from the plan's original `1.120+` to `^1.124` and resolved to 1.141 (latest at install time).
- **`optimizeDeps.exclude: ["@cesium/engine", "cesium"]`**: required to bypass a known Vite + @zip.js subpath-import incompatibility in current Cesium. Slightly slower cold load, but the only working configuration.
- **Variable TTF fonts** instead of WOFF2 for now: all three fonts (Bricolage Grotesque, Geist, JetBrains Mono) shipped as variable TTF directly from upstream open-source repos. WOFF2 subsetting deferred to Phase 7's polish pass (per plan).
- **Cesium `scene.skyAtmosphere/sun/moon/skyBox` are now optional in TS types**: added null-guards.

## Required signups (before any later phase needs them)

| Service | Required for | Status |
|---|---|---|
| Cesium Ion token (`VITE_CESIUM_ION_TOKEN`) | Phase 0 globe rendering | ⏳ User action — see [docs/api-keys-setup.md](../api-keys-setup.md) |
| NASA FIRMS (`FIRMS_MAP_KEY`) | Phase 1 satellite hotspots | ⏳ User action |
| WAQI / AQICN (`WAQI_TOKEN`) | Phase 1 AQ pollutant split | ⏳ User action |

The app boots and serves traffic without any keys; the globe page gracefully shows a setup notice until the Cesium Ion token is provided.

## Next

Run `go phase 1` once the three free tokens are added to `.env`.
