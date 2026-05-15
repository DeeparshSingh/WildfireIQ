# Contributing

WildfireIQ Kamloops is a research artifact produced under a TRU Sustainability Research Grant. The author isn't actively soliciting external contributions during the grant period, but issues and pull requests are welcome and will be reviewed when bandwidth allows.

## Filing an issue

Before opening one, please check:
- **Is this an upstream data issue?** Most "wrong fire status" / "AQHI looks off" reports turn out to be the upstream feed. Compare against BC Wildfire Service or ECCC GeoMet first.
- **Is this a bootstrap issue?** Many parquets are derived. If a chart is empty, try `make bootstrap` then `make seasonal-metrics`.

If filing a bug, include:
- Browser + version (or `curl` invocation for backend issues).
- The exact URL or endpoint.
- What you expected vs. what you got.

## Filing a PR

1. Fork → branch → PR against `main`.
2. Run `make test` and `cd apps/web && pnpm test` locally — both must pass.
3. Run `make typecheck` — TypeScript must stay green.
4. Run `make build` to confirm the production bundle still compiles.
5. Add or update tests for any code you touched. We don't enforce coverage thresholds, but new untested code won't be merged.
6. Don't change the visible API contract (`/api/*` endpoint shapes) without a deprecation note in the PR description.
7. Keep commits small and message them in the existing project style — present tense, no fluff, explain the *why* over the *what*.

## Code style

- **TypeScript** — Biome, default config. Strict TS, no `any` in app code.
- **Python** — ruff + ruff-format. Type hints required on public functions. Docstrings on every router, ingest job, and ML module.
- **No comments that describe *what* the next line does.** Comments explain *why* — non-obvious decisions, trade-offs, references to data quirks.
- **Numbers always with units. Times always with timezones.**

## Areas where help is welcome

- Replacing the synthetic CMIP6 placeholder with a real ClimateData.ca pull.
- ONNX bundle for the 21-model AQ forecaster.
- Additional historical fire sources (Indigenous Fire Management Council, FN-led data partnerships).
- iPad device-on-glass usability testing.
- Translations of the FireSmart checklist + AQ health guidance.

## Code of conduct

Standard Contributor Covenant. Be kind. Wildfire and air-quality data is about real people in real danger — keep that energy in conversations.
