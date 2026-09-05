# WildfireIQ Kamloops — top-level Make targets.
#
# Use these from the repo root. Each target wraps the corresponding `uv run`
# invocation so the contract documented in the model cards and Phase 3 spec
# stays accurate (`make train-risk`, `make train-aq`, etc.).

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
	@echo "  make bootstrap         One-shot pull of historical + static datasets"
	@echo "  make ingest-all        Run every recurring ingest job once"
	@echo "  make train-risk        Train the LightGBM wildfire-risk classifier"
	@echo "  make train-aq          Train the 21-model AQ quantile forecaster"
	@echo "  make seasonal-metrics  Rebuild data/processed/seasonal_metrics.parquet"
	@echo "  make fires-unified     Rebuild data/processed/fires_unified.parquet (current + historical)"
	@echo "  make region-weather    Rebuild each region's daily weather archive"
	@echo "  make risk-features     Rebuild risk features + per-cell density (all regions)"
	@echo "  make assistant-smoke   One live assistant call (needs OPENROUTER_API_KEY)"
	@echo "  make assistant-eval    Live eval suite across every data surface (~30 calls)"
	@echo "  make lint              Ruff check the backend"
	@echo "  make research-assets   Mirror model cards + plots into apps/web/public/research/"
	@echo "  make test              Run the Python test suite"
	@echo "  make typecheck         Run TypeScript typecheck for the frontend"
	@echo "  make build             Production-build the frontend"
	@echo ""

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

.PHONY: fires-unified
fires-unified:
	$(PY_MOD) wildfireiq_api.ml.fires_unified

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
# Research artifacts
# ────────────────────────────────────────────────────────────────────────

.PHONY: research-assets
research-assets:
	@mkdir -p apps/web/public/research
	@cp -f documents/model-cards/*.md apps/web/public/research/ 2>/dev/null || true
	@cp -f data/models/wildfire_risk_v1/metrics.json apps/web/public/research/wildfire_risk_v1.metrics.json 2>/dev/null || true
	@cp -f data/models/aq_forecaster_v1/metrics.json apps/web/public/research/aq_forecaster_v1.metrics.json 2>/dev/null || true
	@echo "Mirrored model cards + metrics into apps/web/public/research/"

# ────────────────────────────────────────────────────────────────────────
# Tests & build
# ────────────────────────────────────────────────────────────────────────

.PHONY: lint
lint:
	cd apps/api && uv run ruff check wildfireiq_api tests
	cd apps/api && uv run ruff format --check wildfireiq_api tests

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

.PHONY: typecheck
typecheck:
	cd apps/web && npx tsc --noEmit

.PHONY: build
build:
	cd apps/web && npx vite build
