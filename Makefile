# WildfireIQ Kamloops — top-level Make targets.
#
# Use these from the repo root. Each target wraps the exact command the
# documentation refers to, so `make train-risk` in a model card means one
# thing and keeps meaning it.

SHELL := /bin/bash
.DEFAULT_GOAL := help

UV       := uv run --project apps/api
PY_MOD   := $(UV) python -m

# ────────────────────────────────────────────────────────────────────────
# Help
# ────────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo "WildfireIQ — make targets"
	@echo ""
	@echo "  make dev               Start the API and the web app together (same as ./start.sh)"
	@echo "  make bootstrap         One-shot pull of historical + static datasets"
	@echo "  make ingest-all        Run every recurring ingest job once"
	@echo "  make train-risk        Train the LightGBM wildfire-risk classifier"
	@echo "  make train-aq          Train the 21-model AQ quantile forecaster"
	@echo "  make seasonal-metrics  Rebuild data/processed/seasonal_metrics.parquet"
	@echo "  make region-weather    Rebuild each region's daily weather archive"
	@echo "  make risk-features     Rebuild risk features + per-cell density (all regions)"
	@echo "  make assistant-smoke   One live assistant call (needs an OpenRouter key in Settings)"
	@echo "  make assistant-eval    Live eval suite across every data surface (~30 calls)"
	@echo "  make serve             Build the web app and serve everything on one port"
	@echo "  make admin-token       Print this deployment's admin token"
	@echo "  make pause             Print a signed pause command (needs your signing key)"
	@echo "  make resume            Print a signed resume command"
	@echo "  make owner             Show your signing key fingerprint"
	@echo "  make check             Everything below, in order — run this before pushing"
	@echo "  make lint              Ruff (backend) + Biome (frontend)"
	@echo "  make format            Apply Ruff and Biome formatting"
	@echo "  make test              Both test suites (backend + frontend)"
	@echo "  make test-live         Ingest smoke tests against the real upstream feeds"
	@echo "  make typecheck         Run TypeScript typecheck for the frontend"
	@echo "  make build             Production-build the frontend"
	@echo ""

# ────────────────────────────────────────────────────────────────────────
# Run
# ────────────────────────────────────────────────────────────────────────

.PHONY: dev
dev:
	./start.sh

.PHONY: serve
serve:
	./start.sh --serve

# ── Owner control ───────────────────────────────────────────────────────
# `admin-token` reads whatever token this deployment is using: the configured
# one, or the one generated on first boot. The rest sign commands with the key
# in ~/.wildfireiq, so they only work on the owner's own machine.

.PHONY: admin-token
admin-token:
	@$(UV) python -c "from wildfireiq_api.owner import admin_token; from wildfireiq_api.settings import get_settings; print(admin_token(get_settings().admin_token))"

.PHONY: owner
owner:
	@$(UV) python scripts/owner.py whoami

.PHONY: pause
pause:
	@$(UV) python scripts/owner.py pause "$(MSG)"

.PHONY: resume
resume:
	@$(UV) python scripts/owner.py resume

# ────────────────────────────────────────────────────────────────────────
# Data
# ────────────────────────────────────────────────────────────────────────

.PHONY: bootstrap
bootstrap:
	$(UV) python scripts/ingest/bootstrap.py

.PHONY: ingest-all
ingest-all:
	$(UV) python scripts/ingest/bootstrap.py --skip-bootstrap

.PHONY: seasonal-metrics
seasonal-metrics:
	$(PY_MOD) wildfireiq_api.ml.seasonal_metrics

.PHONY: region-weather
region-weather:
	$(PY_MOD) wildfireiq_api.scheduler run derived_region_weather

.PHONY: risk-features
risk-features:
	$(PY_MOD) wildfireiq_api.ml.features

# ────────────────────────────────────────────────────────────────────────
# Training
# ────────────────────────────────────────────────────────────────────────

.PHONY: train-risk
train-risk:
	$(PY_MOD) wildfireiq_api.ml.train_risk

.PHONY: train-aq
train-aq:
	$(PY_MOD) wildfireiq_api.ml.train_aq

# ────────────────────────────────────────────────────────────────────────
# Tests & build
# ────────────────────────────────────────────────────────────────────────

.PHONY: lint
lint:
	cd apps/api && uv run ruff check wildfireiq_api tests
	cd apps/api && uv run ruff format --check wildfireiq_api tests
	cd apps/web && npx biome check .

.PHONY: format
format:
	cd apps/api && uv run ruff format wildfireiq_api tests
	cd apps/web && npx biome check --write .

.PHONY: prune-raw
prune-raw:
	cd apps/api && uv run python -m wildfireiq_api.ingest.prune

# One real call to OpenRouter, to prove the key and the loop work end to end.
# Everything else about the assistant is covered offline by test_assistant.py,
# so this is the only target that spends anything. Costs a fraction of a cent.
# Override the question: make assistant-smoke Q="how smoky is it in Kelowna?"
.PHONY: assistant-smoke
assistant-smoke:
	cd apps/api && uv run python -m wildfireiq_api.assistant.smoke $(if $(Q),"$(Q)",)

# The live evaluation suite: ~30 questions across every data surface, each
# with expectations about tool choice, grounding, scope and refusal. Costs
# roughly $0.003 a case. ONLY=<substring> runs a subset.
.PHONY: assistant-eval
assistant-eval:
	cd apps/api && uv run python -m wildfireiq_api.assistant.evals $(if $(ONLY),--only $(ONLY),) $(if $(VERBOSE),--verbose,)

.PHONY: test
test:
	cd apps/api && uv run pytest -q
	cd apps/web && npx vitest run

.PHONY: test-api
test-api:
	cd apps/api && uv run pytest -q

.PHONY: test-web
test-web:
	cd apps/web && npx vitest run

# The three ingest smoke tests, which call the real upstream feeds. Excluded
# from `make test` so the default run works offline and cannot fail because
# DataBC is having a bad afternoon.
.PHONY: test-live
test-live:
	cd apps/api && uv run pytest -m live -q -s

.PHONY: typecheck
typecheck:
	cd apps/web && npx tsc --noEmit

.PHONY: build
build:
	cd apps/web && npx vite build

# The full pre-push gate. Ordered cheapest-first so it fails fast.
.PHONY: check
check: lint typecheck test build
	@echo ""
	@echo "All checks passed."

