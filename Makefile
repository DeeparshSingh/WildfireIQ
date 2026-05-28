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
	@echo "  make seasonal-metrics  Rebuild data/processed/seasonal_metrics.parquet (Phase 6)"
	@echo "  make fires-unified     Rebuild data/processed/fires_unified.parquet (current + historical)"
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

.PHONY: test
test:
	cd apps/api && uv run pytest -q

.PHONY: typecheck
typecheck:
	cd apps/web && npx tsc --noEmit

.PHONY: build
build:
	cd apps/web && npx vite build
