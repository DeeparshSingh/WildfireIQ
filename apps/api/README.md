# WildfireIQ API

The FastAPI backend: ingest jobs, the two LightGBM models, the REST API, and
the assistant. Run it from the repository root with `./start.sh` (both halves)
or on its own:

```bash
cd apps/api
uv sync
uv run uvicorn wildfireiq_api.main:app --reload --port 8000
```

Interactive API docs are served at http://localhost:8000/docs.

How the pieces fit together is documented once, at the repository level:
`documents/how-it-works.md` for the data flow and `documents/architecture.md`
for the engineering detail.
