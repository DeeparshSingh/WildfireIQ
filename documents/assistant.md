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
each of the four modelled regions, the province-wide active-fire count with
the largest incident and the nearest one to Kamloops, evacuation orders and
alerts in effect, AQHI and PM2.5, current Kamloops weather, and days since
meaningful rain.

That costs about 150 tokens and it means the common question is answered in
one model turn with no tool calls at all, instead of three turns and a
LightGBM run. It is rebuilt at most once a minute and shared across users,
since it contains nothing user-specific.

Every line is province-wide unless it names a place, and the prompt says so
explicitly. That rule is there because the first live answer this assistant
gave closed with "nothing in the Kamloops area per the current feed" — a
proximity claim inferred from a province-wide count. The brief now states
the distance to the nearest incident outright rather than leaving room for
the inference.

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

**Geometry is computed, never narrated.** Tools that return a point relative
to somewhere give a compass direction and the nearest named town alongside
the distance. The second live answer this assistant produced placed a fire
77 km east-southeast of Kamloops "southwest near Falkland" — wrong quadrant,
wrong town, from coordinates it was left to interpret itself. Spherical
trigonometry is not something to leave to prose, so the tools now do it.

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

Measured across the 32-case evaluation suite, not estimated.

| | Prompt tokens | Cost | Latency |
|---|---:|---:|---:|
| Answered from the brief alone | ~6,000 | $0.0007-$0.0009 | 2-8 s |
| One or more tools | 12,000-20,000 | $0.0002-$0.0023 | 4-25 s |
| **Whole 32-case sweep** | — | **$0.020-$0.043** ($0.0006-$0.0013/case) | median **6-14 s** |

The per-turn floor is about 6,100 tokens: ~1,400 for the system prompt,
~150 for the brief, and ~4,700 for the 25 tool schemas, all re-sent on
every turn of a run. A third of the suite needs no tool at all, which is
the brief paying for itself.

The cost and latency columns are ranges because they are ranges: the figures
come from repeated full sweeps, and the same question costs roughly twice as
much on one run as another depending on how many turns the model takes and how
much it writes. Quoting a single number here would be false precision. The
upper end of each range is the one to budget against.

### Where the time went

The first sweep ran at a median of 16 s and a worst case of **90 s**. Two
findings fixed that, and both came from measuring rather than guessing:

**GLM 5.3 Flash is a reasoning model, and OpenRouter reserves its thinking
allowance before the answer is written.** A turn that thought hard about a
forecast spent the whole `max_tokens` budget on reasoning and returned
empty — billing 1,900 completion tokens for a blank answer. Four of the
first thirty-two cases failed that way. Raising the ceiling to 3,000 fixed
the blanks but let answers sprawl to 3,600 tokens.

**Capping reasoning effort was the real lever.** Setting
`reasoning: {"effort": "low"}` cut the median from 16 s to 6 s and the
worst case from 90 s to under 30 s, with the evaluation suite still at
32/32 — the thinking was not buying correctness, only time. It is a
setting (`ASSISTANT_REASONING_EFFORT`) because a harder model or a harder
question might need more.

Three further things keep the total down: the brief, which removes the
tool round trip from the common case; per-tool result caching (60 s for
live feeds, 15 minutes for the risk grid, an hour for documentation and
climate history), sound because the underlying parquet only moves when an
ingest job runs; and dropping duplicate tool calls within a turn.

The tool schemas dominate the token floor, and they stay verbose on
purpose: their descriptions are what let the model reach for
`get_health_guidance` on an asthma question without being told to.
Trimming their prose bought back about 340 tokens a turn — real, but a
rounding error beside the cost of picking the wrong tool.

## Configuration

The OpenRouter key is entered in the app's Settings panel (the key icon in
the top bar) and held by the runtime key store in `keys.py`; it is not an
environment variable. The rest is configuration:

```bash
ASSISTANT_MODEL=z-ai/glm-5.3-flash  # default
ASSISTANT_MAX_STEPS=5
ASSISTANT_MAX_TOOL_CALLS=12
```

`GET /api/assistant/health` reports `enabled` and `configured` without ever
echoing the key. When `enabled` is false the frontend renders nothing. When
only `configured` is false it shows a muted Ask button that opens the Settings
panel, the one action that can fix it.

## Abuse and spend limits

This is the only endpoint in the backend whose cost is money rather than
CPU, and the platform has no accounts to bill it to. Three limits in
`assistant/guard.py` stand in for access control:

| Limit | Default | Stops |
|---|---|---|
| Per-caller, per minute | 4 | one person or a broken script hammering it |
| Per-caller, per hour | 30 | sustained monopolisation |
| Rolling 24-hour spend | $2.00 | a distributed burst, or a popular day, emptying the account |
| Concurrent runs | 4 | a burst opening fifty upstream connections at once |

Rate limits key on the caller address, which behind a proxy comes from
`X-Forwarded-For` and is therefore spoofable if the app is exposed
directly. That is exactly why the spend ceiling exists and does not
consult it: it is the backstop that does not care who is asking. Spend is
booked from OpenRouter's own reported charge after each run, so the
ceiling can be overshot by at most the runs already in flight.

All three are in-process, matching the rest of this backend — one uvicorn
process, no Redis. A multi-process deployment would need shared state.
`GET /api/assistant/health` publishes the current numbers.

## Resisting misuse

- The system prompt is rebuilt server-side every request. `sanitise_history`
  accepts only `user` and `assistant` roles, so a `system` turn posted by a
  caller cannot arrive with the authority of the real one, and the Pydantic
  schema rejects it before that.
- **Tool results are data, never instructions.** They carry text from
  upstream feeds — fire names, evacuation event names, document extracts —
  which the assistant reports but never obeys.
- Refusals are evaluated, not assumed. The suite includes prompt
  extraction, a persona override demanding the assistant call a High-risk
  area "completely safe", pressure to fabricate a figure the platform does
  not hold, off-topic coding requests, and general-knowledge questions.
- UI effects come from a closed, server-validated vocabulary, and
  `navigate` accepts in-app paths only.

## Testing

Two layers, and the split is deliberate.

`apps/api/tests/test_assistant.py` — 81 tests, entirely offline. A
scripted client replays model turns, so the loop, budgets, parallel
fan-out, tool errors, malformed arguments, event ordering, the safety
tripwire, the rate limiter and the spend ceiling are all exercised without
spending anything upstream. This runs in CI.

`make assistant-eval` — 32 live cases across every data surface, each
declaring which tools should run, what the answer must and must not
contain, and whether an effect or safety notice is expected. It costs
about $0.05 a sweep and catches what a scripted model cannot: whether the
real model picks the right tool, honours the grounding rules, and refuses
what it should. Both regressions fixed after the first live runs — the
inferred proximity claim and the narrated compass bearing — are now cases
in it. `make assistant-smoke` runs a single traced question.
