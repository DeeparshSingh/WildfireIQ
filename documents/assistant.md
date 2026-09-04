# The WildfireIQ assistant

A tool-using agent built into the platform. It answers from the project's
own live data and its own trained models rather than from a language
model's memory, and it can act on the interface — flying the globe,
switching layers, opening a page.

Backed by **GLM 5.3 Flash** (`z-ai/glm-5.3-flash`) through OpenRouter.

## Why a harness and not a chat window

A chat window bolted onto a data platform can only paraphrase whatever was
pasted into its prompt. The interesting questions here are specific —
*"are there fires near Logan Lake?"*, *"how does this summer compare with
2023?"*, *"is the air safe to run in?"* — and every one of them needs a
different slice of a different dataset. So the model is given hands
instead of a summary: 25 typed, read-only functions over the same parquet
files and the same LightGBM models the map and the dashboards read.

Three design decisions follow from that.

**Tools run in-process.** They call `routers/_data.py`, `ml/risk_infer.py`
and `ml/aq_infer.py` directly rather than looping back through HTTP. One
less hop, one less failure mode, and a tool can aggregate 96,356 historical
fires without serialising them through an endpoint first.

**Every result carries provenance.** A `ToolResult` names its source and
the timestamp of the underlying data, and those travel to the browser as
citation chips. An answer that cannot say where its numbers came from is
not an answer this project wants to give.

**Results are bounded.** Each tool result is capped at 8,000 characters
before it reaches the model. Tools are expected to aggregate; one that
tries to return a raw table gets told to narrow its filter.

## The situation brief

Before the model sees the question it sees a brief: today's AI risk for
each of the four modelled regions, the active-fire count and the largest
incident, evacuation orders and alerts in effect, AQHI and PM2.5, current
Kamloops weather, and days since meaningful rain.

That costs roughly 250 tokens — about two hundredths of a cent — and it
means the common question is answered in one model turn with no tool calls
at all, instead of two turns and a LightGBM run. It is rebuilt at most once
a minute and shared across users, since it contains nothing user-specific.
`GET /api/assistant/brief` returns it verbatim: an assistant whose
grounding cannot be inspected cannot be audited.

## The loop

One question becomes a sequence of model turns. A turn either answers or
asks for tools. If it asks, every tool it requested runs **concurrently**,
the results go back as tool messages, and the loop takes another turn.

Budgets, defaulting to five steps and twelve tool calls:

- On the final permitted step, and once the tool budget is spent, the tools
  are **withdrawn** from the request. The model then has no option but to
  answer from what it already has — an agent that runs out of budget
  mid-plan should still reply.
- A tool failure is returned to the conversation rather than aborting the
  run, because "that place is not in the gazetteer, here are four that are"
  is something the model can act on.
- Whatever happens, the stream ends in a terminal event.

## Streaming

`POST /api/assistant/chat` returns Server-Sent Events. The frames are the
harness's own events, so anything the agent can report the browser can
render:

| Event | Meaning |
|---|---|
| `start` | Model and tool count for this run |
| `status` | A new step began |
| `token` | A slice of streamed text |
| `step_end` | That text was a plan, not the answer — move it to the activity trail |
| `tool_call` | A tool was requested, with its arguments |
| `tool_result` | It finished: ok, cached, duration, one-line summary |
| `effect` | An instruction for the UI (see below) |
| `safety` | Emergency notice, emitted before the model runs |
| `sources` | Deduplicated provenance for the answer |
| `suggestions` | Three follow-up questions |
| `usage` | Tokens, real OpenRouter cost, tool count, wall time |
| `done` | Final answer text |
| `error` | Something failed; the message is safe to show |

`?stream=false` collects a whole run into one JSON body, which is how the
endpoint is exercised with a single `curl`.

## Effects

Three tools return *effects* rather than data: `show_on_map`,
`set_map_layer`, `open_page`. The vocabulary is closed — `fly_to`,
`set_layer`, `navigate` — and validated server-side, so the model can pick
an action and fill in its arguments but cannot invent one. `navigate` only
accepts in-app paths.

## The toolset

| Group | Tools |
|---|---|
| Risk | `get_wildfire_risk` |
| Fires | `get_active_fires`, `get_satellite_hotspots`, `get_historical_fires` |
| Evacuation | `check_evacuation_status`, `list_evacuation_orders` |
| Air | `get_air_quality`, `get_air_quality_forecast`, `get_health_guidance`, `get_smoke_history`, `get_smoke_plume_forecast` |
| Weather | `get_weather`, `get_fire_weather_index`, `get_season_context` |
| Climate | `get_seasonal_history`, `get_climate_trends`, `get_fire_danger_projection` |
| Preparedness | `get_firesmart_actions` |
| Reference | `search_documentation`, `get_model_performance`, `get_data_freshness`, `resolve_place` |
| Interface | `show_on_map`, `set_map_layer`, `open_page` |

`GET /api/assistant/tools` publishes the live catalogue.

Location-aware tools take a `place` name or a `lat`/`lon` pair. Place names
resolve against an **offline gazetteer** — the four region anchors, the
fourteen Kamloops neighbourhoods the FireSmart hub already ships, and about
eighty BC communities. No geocoder key, no network round trip, and an
unknown name comes back as unknown with near-miss suggestions instead of a
confident coordinate in the wrong province.

Asking for a place outside the model's four regions returns a
`coverage_warning` naming the distance to the nearest modelled hexagon, so
the assistant reports it as out of coverage rather than as a reading.

## Safety

- A regex tripwire runs **before** the model on every question. Wording
  like "should I evacuate" or "fire in my yard" emits a `safety` event
  carrying 911, EmergencyInfoBC and the BC Wildfire Service reporting line.
  It is deterministic, so those numbers reach the screen even if the model
  is slow, wrong, or down.
- The system prompt forbids stating a number that did not come from the
  brief or a tool, requires coverage and freshness caveats to be passed on
  rather than smoothed over, and routes every health question through
  `get_health_guidance`.
- Evacuation wording is fixed: ORDER means leave now, ALERT means be ready.
  Nothing may call an area safe on the strength of a model score.

## Privacy

The backend is stateless. The browser owns the transcript and sends it back
on each request; nothing is stored server-side, and the structured log
records tokens, cost, latency and which tools ran — never message content.

The client's `context` — current page, camera position, FireSmart profile —
lives for the length of one request. `sanitise_history` accepts only `user`
and `assistant` turns, so a `system` role smuggled in by a caller cannot
reach the model with the authority of the real system prompt, which is
rebuilt server-side every time.

## Cost

At GLM 5.3 Flash's rates a question with the brief, the tool schemas and one
round of tool results runs roughly 4,000-8,000 input tokens and a few
hundred output — a few hundredths of a cent. Every run reports its actual
OpenRouter charge in the `usage` event.

Two things keep it there: the brief, which removes tool calls from the
common case, and per-tool result caching (60 s for live feeds, 15 minutes
for the risk grid, an hour for documentation and climate history), which is
sound because the underlying parquet only moves when an ingest job runs.

## Configuration

```bash
OPENROUTER_API_KEY=sk-or-...        # required; without it the launcher hides
ASSISTANT_MODEL=z-ai/glm-5.3-flash  # default
ASSISTANT_MAX_STEPS=5
ASSISTANT_MAX_TOOL_CALLS=12
```

`GET /api/assistant/health` reports `enabled` and `configured` without ever
echoing the key. The frontend renders nothing at all when either is false,
rather than offering a button that can only produce an error.

## Testing

`apps/api/tests/test_assistant.py` runs entirely offline: a scripted client
replays model turns, so the loop — budgets, parallel fan-out, tool errors,
malformed arguments, event ordering, the safety tripwire — is exercised
without spending anything upstream. `make assistant-smoke` is the one
target that does spend, and it makes a single call.
