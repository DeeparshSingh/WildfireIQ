# Contributing

WildfireIQ Kamloops was built under a Thompson Rivers University Sustainability
Research Grant. Issues and pull requests are welcome and are reviewed as time
allows.

## Before filing an issue

- **Is it the upstream feed?** Most "wrong fire status" or "AQHI looks off"
  reports turn out to be the source. Compare against the BC Wildfire Service
  or ECCC pages first.
- **Is the data built?** Empty charts on a fresh clone usually mean the
  one-time bootstrap has not run: `./start.sh --bootstrap`.

Include the browser and version (or the `curl` command for API issues), the
exact URL or endpoint, and what you expected versus what you saw.

## Pull requests

1. Branch from `main`.
2. Run the full check locally — all four must pass:
   ```bash
   make lint && make test && make typecheck && make build
   cd apps/web && pnpm test
   ```
3. Add or update tests for anything you changed. There is no coverage
   threshold, but untested new code is not merged.
4. Do not change an `/api/*` response shape without saying so in the PR.
5. Commit messages: present tense, explain the *why*, no filler.

## Code style

- **TypeScript** — Biome (`pnpm lint`), strict TypeScript, no `any` in app code.
- **Python** — `ruff check` and `ruff format`. Type hints on public functions.
  A docstring on every router, ingest job, and ML module.
- Comments explain *why*, never what the next line does. Numbers carry units;
  times carry time zones.
- Delete dead code. Do not comment it out.

## Where help is most useful

- Replacing the synthetic CMIP6 placeholder with a real ClimateData.ca pull
  (`ingest/climatedata_projections.py`; the page and endpoints already exist).
- Adding lightning-strike and vegetation-greenness features to the risk model
  (the two largest gaps named in its model card).
- A fire-history source for provinces other than BC, which is what stands
  between the risk model and coverage outside the province
  (see `documents/how-it-works.md`, "Extending the platform").
- On-device tablet testing of the globe.

## Conduct

Standard Contributor Covenant. Wildfire and air-quality data is about real
people in real danger; keep that in mind in every conversation.
