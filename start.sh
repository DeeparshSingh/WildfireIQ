#!/usr/bin/env bash
# Start WildfireIQ locally: the FastAPI backend on :8000 and the web app on :5173.
#
#   ./start.sh              start both for development (two ports, hot reload)
#   ./start.sh --serve      build the web app and serve everything on one port
#   ./start.sh --bootstrap  also pull the historical datasets first (one-time, ~10 min)
#   ./start.sh --help
#
# --serve is the one to deploy with: the API serves the built web app, so the
# browser and the API share one origin and there is no CORS to configure.
#
# Stop with Ctrl-C; both processes shut down together.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'; RESET=$'\033[0m'
say()  { printf '%s\n' "$*"; }
ok()   { printf '%s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
fail() { printf '%s✗%s %s\n' "$RED" "$RESET" "$*" >&2; exit 1; }

BOOTSTRAP=0
SERVE=0
for arg in "$@"; do
  case "$arg" in
    --bootstrap) BOOTSTRAP=1 ;;
    --serve) SERVE=1 ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) fail "unknown option: $arg (try --help)" ;;
  esac
done

say "${BOLD}WildfireIQ${RESET} ${DIM}· local start${RESET}"

# ── 1. Tools ────────────────────────────────────────────────────────────
command -v node >/dev/null || fail "Node.js is required (v20+). https://nodejs.org"
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[ "$NODE_MAJOR" -ge 20 ] || fail "Node.js 20 or newer is required (found $(node -v))."
command -v pnpm >/dev/null || fail "pnpm is required. Install with: npm install -g pnpm"
command -v uv   >/dev/null || fail "uv is required for the Python backend. https://docs.astral.sh/uv/"
ok "node $(node -v), pnpm $(pnpm -v), uv $(uv --version | awk '{print $2}')"

# ── 2. Environment file ─────────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  say "  Created .env from .env.example."
fi
say "  ${DIM}API keys (Cesium, FIRMS, WAQI, OpenRouter) are entered in the app: the key"
say "  icon in the top bar. Nothing goes in .env.${RESET}"

# ── 3. Dependencies (skipped when already present) ──────────────────────
if [ ! -d node_modules ] || [ ! -d apps/web/node_modules ]; then
  say "  Installing web dependencies…"; pnpm install --silent
fi
if [ ! -d apps/api/.venv ]; then
  say "  Installing Python dependencies…"; (cd apps/api && uv sync --quiet)
fi
ok "dependencies ready"

# ── 4. Data ─────────────────────────────────────────────────────────────
# The historical datasets (fire archive, 27 years of weather) are pulled once.
# Live feeds refresh on their own the moment the API starts.
if [ "$BOOTSTRAP" -eq 1 ] || [ ! -f data/processed/fires_historical.parquet ]; then
  if [ "$BOOTSTRAP" -eq 0 ]; then
    say "  No historical data yet — running the one-time bootstrap (about 10 minutes)."
  fi
  (cd apps/api && uv run python ../../scripts/ingest/bootstrap.py)
  ok "historical data ready"
fi

# ── 5. Run ──────────────────────────────────────────────────────────────
if [ "$SERVE" -eq 1 ]; then
  say "  Building the web app…"
  pnpm --filter @wildfireiq/web build >/dev/null
  ok "web app built"
  say ""
  say "  ${BOLD}http://localhost:8000${RESET}  ${DIM}app and API on one origin (docs at /docs)${RESET}"
  say "  ${DIM}Ctrl-C stops it. Admin token: make admin-token${RESET}"
  say ""
  cd apps/api && exec uv run uvicorn wildfireiq_api.main:app --host 0.0.0.0 --port 8000
fi

say ""
say "  API   ${BOLD}http://localhost:8000${RESET}  ${DIM}(docs at /docs)${RESET}"
say "  Web   ${BOLD}http://localhost:5173${RESET}"
say "  ${DIM}Ctrl-C stops both.${RESET}"
say ""
exec pnpm dev
