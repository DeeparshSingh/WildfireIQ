"""The WildfireIQ assistant: a tool-using agent over the platform's own data.

The package is deliberately self-contained. Nothing else in the backend
imports from it, and it imports the rest of the backend read-only, so the
assistant can be disabled (or fail entirely) without touching the map, the
dashboards, or the ingest pipeline.

Layout:
  openrouter.py  transport — streaming chat completions, tool-call assembly
  gazetteer.py   offline place → coordinate resolution for British Columbia
  tools/         the agent's hands: ~20 typed functions over live data
  brief.py       the situation brief prepended to every conversation
  prompts.py     system prompt assembly
  harness.py     the agent loop, budgets, and the event stream it emits
  router.py      HTTP surface (SSE)
"""
