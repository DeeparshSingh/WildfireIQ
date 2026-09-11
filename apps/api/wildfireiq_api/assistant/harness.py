"""The agent loop.

One question becomes a sequence of model turns. A turn either answers or
asks for tools; if it asks, every requested tool runs concurrently, the
results go back as tool messages, and the loop takes another turn. It ends
when the model answers, when the budget runs out, or when something breaks
— and in all three cases the caller gets a terminal event rather than a
dangling stream.

Everything the caller sees is an `Event`. The HTTP layer turns those into
SSE frames and the test suite reads them directly, so the transport and
the agent share exactly one contract.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator, Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

import structlog

from ..keys import keystore
from ..settings import Settings, get_settings
from . import tools as toolkit
from .brief import build_brief
from .openrouter import OpenRouterClient, OpenRouterError, StepResult, ToolCall, Usage
from .prompts import build_system_prompt

log = structlog.get_logger(__name__)

#: How much conversation history to accept from the client. The server is
#: stateless — the browser owns the transcript — so this is the only thing
#: standing between a long session and an expensive prompt.
MAX_HISTORY_MESSAGES = 20
MAX_MESSAGE_CHARS = 6000


@dataclass(slots=True)
class Event:
    """One thing that happened, on its way to the browser."""

    name: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChatRequest:
    messages: list[dict[str, str]]
    context: dict[str, Any] | None = None


# ─── Safety tripwire ─────────────────────────────────────────────────
#
# A model that is mostly right is not good enough when someone is typing
# "there's fire in my yard". This runs before the model does, deterministically,
# so the emergency numbers reach the screen even if the model is slow, wrong,
# or down.

_URGENT_PATTERNS = (
    r"\bcall(ing)? 911\b",
    r"\b(i|we)('?m| am| are)? ?(trapped|surrounded|evacuating)\b",
    r"\bfire (is )?(in|on|at|near|outside) my\b",
    r"\b(see|smell|seeing|smelling) (the )?(flames|smoke)\b.*\b(house|home|yard|street)\b",
    r"\bshould (i|we) (evacuate|leave|get out)\b",
    r"\bdo (i|we) (need|have) to (evacuate|leave)\b",
    r"\bhouse is on fire\b",
    r"\bembers?\b.*\b(landing|on my roof)\b",
)
_URGENT_RE = re.compile("|".join(_URGENT_PATTERNS), re.IGNORECASE)

EMERGENCY_NOTICE = (
    "If you are in immediate danger, call 911. For official evacuation orders "
    "check emergencyinfobc.gov.bc.ca, and report a wildfire to the BC Wildfire "
    "Service at 1-800-663-5555 (or *5555 from a cell phone)."
)


def looks_urgent(text: str) -> bool:
    return bool(_URGENT_RE.search(text or ""))


# ─── Follow-up suggestions ───────────────────────────────────────────
#
# Generated from which tools ran, not by a second model call. Suggestions
# are worth about three cents a thousand from a model and nothing at all
# from a dictionary, and the dictionary never hallucinates a capability.

_FOLLOW_UPS: dict[str, tuple[str, ...]] = {
    "get_wildfire_risk": (
        "Why is the risk at that level today?",
        "How does that compare with the other regions?",
    ),
    "get_active_fires": (
        "Show the closest one on the map",
        "Has anything burned near there before?",
    ),
    "get_satellite_hotspots": ("Are any of those already reported as incidents?",),
    "check_evacuation_status": ("What should I pack in a go-bag?",),
    "list_evacuation_orders": ("Show the evacuation zones on the map",),
    "get_air_quality": ("Will the air improve tomorrow?", "Is it safe to exercise outside?"),
    "get_air_quality_forecast": ("What should at-risk people do at that level?",),
    "get_health_guidance": ("How bad has the smoke been this summer?",),
    "get_smoke_history": ("How does this summer compare with 2023?",),
    "get_weather": ("How does that feed into the fire danger?",),
    "get_fire_weather_index": ("What do those component codes actually mean?",),
    "get_seasonal_history": ("Is that a real trend or just noise?",),
    "get_climate_trends": ("What does that imply for the 2040s?",),
    "get_historical_fires": ("What causes most fires around here?",),
    "get_firesmart_actions": ("Which of those matters most?", "Open my checklist"),
    "get_model_performance": ("Where does the model do worst?",),
    "search_documentation": ("What are the model's known limitations?",),
}

_DEFAULT_FOLLOW_UPS = (
    "What's the wildfire risk near me?",
    "Is the air quality safe today?",
    "How can I prepare my home?",
)


def suggest_follow_ups(tool_names: Iterable[str]) -> list[str]:
    out: list[str] = []
    for name in tool_names:
        for suggestion in _FOLLOW_UPS.get(name, ()):
            if suggestion not in out:
                out.append(suggestion)
    if not out:
        out = list(_DEFAULT_FOLLOW_UPS)
    return out[:3]


# ─── History hygiene ─────────────────────────────────────────────────


def sanitise_history(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Keep only well-formed user/assistant turns, newest-bounded.

    The client sends the transcript back on every request, so this is an
    untrusted input: a `system` role slipped in here would be a prompt
    injection with the authority of the real system prompt. Only two roles
    survive, and the system prompt is always built server-side.
    """
    cleaned: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role") or "")
        if role not in {"user", "assistant"}:
            continue
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        cleaned.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})

    cleaned = cleaned[-MAX_HISTORY_MESSAGES:]
    # A conversation that starts on an assistant turn confuses some models
    # and carries no information anyway.
    while cleaned and cleaned[0]["role"] == "assistant":
        cleaned.pop(0)
    return cleaned


# ─── The loop ────────────────────────────────────────────────────────


class AssistantUnavailable(RuntimeError):
    """The assistant is switched off or has no API key."""


def availability(settings: Settings | None = None) -> dict[str, Any]:
    """Whether the assistant can serve, and what it is configured with."""
    settings = settings or get_settings()
    return {
        "enabled": settings.assistant_enabled,
        "configured": bool(keystore.get("openrouter_api_key")),
        # A visitor may bring their own key on each request (X-OpenRouter-Key),
        # so the assistant can be usable even when the server holds none.
        "accepts_visitor_key": True,
        "model": settings.assistant_model,
        "tools": len(toolkit.REGISTRY),
        "max_steps": settings.assistant_max_steps,
        "max_tool_calls": settings.assistant_max_tool_calls,
    }


async def run_conversation(
    request: ChatRequest,
    *,
    settings: Settings | None = None,
    client: OpenRouterClient | None = None,
    api_key: str | None = None,
) -> AsyncIterator[Event]:
    """Run one question to completion, yielding events as they happen."""
    settings = settings or get_settings()
    queue: asyncio.Queue[Event | None] = asyncio.Queue()
    task = asyncio.create_task(_drive(queue, request, settings, client, api_key))
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
    finally:
        if not task.done():
            task.cancel()
            # Let the cancellation actually land so the HTTP call it may be
            # sitting in gets closed rather than leaked.
            await asyncio.gather(task, return_exceptions=True)


async def _drive(
    queue: asyncio.Queue[Event | None],
    request: ChatRequest,
    settings: Settings,
    client: OpenRouterClient | None,
    api_key: str | None = None,
) -> None:
    started = time.perf_counter()
    usage = Usage()
    sources: list[dict[str, Any]] = []
    tools_used: list[str] = []
    answer_parts: list[str] = []
    preamble_parts: list[str] = []

    # Positional-only, so an event carrying a `name` field of its own (a
    # tool_call does) cannot collide with the event's own name.
    async def emit(event_name: str, /, **data: Any) -> None:
        await queue.put(Event(event_name, data))

    try:
        if not settings.assistant_enabled:
            raise AssistantUnavailable("The assistant is disabled on this deployment.")

        history = sanitise_history(request.messages)
        if not history:
            raise ValueError("no user message to answer")
        question = history[-1]["content"]

        if looks_urgent(question):
            await emit("safety", message=EMERGENCY_NOTICE)

        await emit(
            "start",
            model=settings.assistant_model,
            tools_available=len(toolkit.REGISTRY),
        )

        client = client or OpenRouterClient(
            # The visitor's own key wins for this request; the owner's stored
            # key is the default for everyone else.
            api_key=api_key or keystore.get("openrouter_api_key"),
            model=settings.assistant_model,
            referer=settings.assistant_referer,
            title=settings.assistant_title,
            timeout_s=settings.assistant_timeout_s,
            reasoning_effort=settings.assistant_reasoning_effort,
        )

        # Blocking: reads parquet, may run LightGBM on a cold cache.
        brief = await asyncio.to_thread(build_brief)
        system_prompt = build_system_prompt(
            brief=brief,
            context=request.context,
            max_steps=settings.assistant_max_steps,
            max_tool_calls=settings.assistant_max_tool_calls,
        )
        conversation: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *history,
        ]

        tool_budget = settings.assistant_max_tool_calls
        deadline = time.monotonic() + settings.assistant_timeout_s

        for step in range(settings.assistant_max_steps):
            out_of_time = time.monotonic() > deadline
            last_step = step == settings.assistant_max_steps - 1
            # On the final permitted step, or once the budget is gone, the
            # tools are withdrawn. The model then has no option but to
            # answer from what it already has, which is what we want — an
            # agent that runs out of budget mid-plan should still reply.
            offer_tools = bool(tool_budget) and not last_step and not out_of_time

            await emit("status", phase="thinking", step=step)

            step_result = await _one_step(
                client,
                conversation,
                offer_tools=offer_tools,
                on_text=lambda text: queue.put(Event("token", {"text": text})),
                max_tokens=settings.assistant_max_output_tokens,
            )
            usage = usage + step_result.usage

            if step_result.truncated:
                # The turn hit its output ceiling. On a reasoning model that
                # usually means thinking ate the whole allowance, which is
                # how an answer goes missing while still being billed.
                log.warning(
                    "assistant.step.truncated",
                    step=step,
                    content_chars=len(step_result.text),
                    reasoning_chars=step_result.reasoning_chars,
                )

            if not step_result.tool_calls:
                if step_result.text:
                    answer_parts.append(step_result.text)
                break

            # The text of a turn that ends in tool calls is usually a plan,
            # not an answer — "let me check the fires near Merritt" — so the
            # client moves it out of the answer bubble and into the activity
            # trail. But it is not *always* a plan: a model that writes its
            # whole answer and then calls `show_on_map` in the same turn has
            # already said everything it intends to, and the next turn comes
            # back silent. Four of the first thirty-two live evaluations lost
            # a complete, paid-for answer that way. So it is kept as a
            # fallback, and used only if nothing better arrives.
            if step_result.text.strip():
                preamble_parts.append(step_result.text)
            await emit("step_end", had_tools=True, note=step_result.text.strip() or None)

            calls = _drop_duplicates(step_result.tool_calls)[:tool_budget]
            tool_budget -= len(calls)
            conversation.append(_assistant_tool_message(step_result.text, calls))

            for call in calls:
                await emit("tool_call", id=call.id, name=call.name, arguments=call.arguments[:600])

            executions = await asyncio.gather(*(_run_tool(call) for call in calls))

            for call, execution in zip(calls, executions, strict=True):
                tools_used.append(call.name)
                conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": execution.content_for_model(),
                    }
                )
                await emit(
                    "tool_result",
                    id=call.id,
                    name=call.name,
                    ok=execution.ok,
                    cached=execution.cached,
                    duration_ms=execution.duration_ms,
                    summary=_summarise(execution),
                    error=execution.error,
                )
                if execution.ok and execution.result is not None:
                    for effect in execution.result.effects:
                        await emit("effect", **effect)
                    _record_source(sources, execution.result.source, execution.result.as_of)
        else:
            # Loop ran out of steps without a `break`: the last turn still
            # wanted tools. Its text was withheld as a plan, so say so
            # rather than ending on silence.
            if not answer_parts and not preamble_parts:
                answer_parts.append(
                    "I ran out of research steps before I could finish that one. "
                    "Try asking it in smaller pieces."
                )
                await emit("token", text=answer_parts[-1])

        # An answering turn that produced nothing leaves the preamble as the
        # only thing the model actually said. Better a slightly conversational
        # answer than a blank one.
        final_text = "".join(answer_parts).strip()
        if not final_text and preamble_parts:
            final_text = "\n\n".join(p.strip() for p in preamble_parts).strip()
            log.info("assistant.recovered_answer_from_preamble", chars=len(final_text))
            await emit("recovered", text=final_text)

        if not final_text:
            # Everything upstream succeeded and the model still said nothing.
            # Say that plainly: a blank bubble looks like the app is broken,
            # and the user has no way to tell the difference.
            final_text = (
                "I gathered the data but did not manage to write an answer. "
                "Ask me again, or more narrowly, and it should come through."
            )
            log.warning("assistant.empty_answer", tools=tools_used)
            await emit("token", text=final_text)

        await emit("sources", sources=sources)
        await emit("suggestions", items=suggest_follow_ups(tools_used))
        await emit(
            "usage",
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=round(usage.cost_usd, 6),
            tool_calls=len(tools_used),
            tools=tools_used,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        await emit("done", text=final_text)

        log.info(
            "assistant.answered",
            tools=tools_used,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=round(usage.cost_usd, 6),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    except asyncio.CancelledError:
        raise
    except (AssistantUnavailable, OpenRouterError, ValueError) as exc:
        log.warning("assistant.failed", error=str(exc))
        await emit("error", message=str(exc), kind=type(exc).__name__)
    except Exception as exc:
        log.error("assistant.crashed", error=str(exc), exc_info=True)
        await emit("error", message="The assistant hit an unexpected error.", kind="internal")
    finally:
        await queue.put(None)


async def _one_step(
    client: OpenRouterClient,
    conversation: list[dict[str, Any]],
    *,
    offer_tools: bool,
    on_text: Any,
    max_tokens: int,
) -> StepResult:
    return await client.stream_step(
        conversation,
        toolkit.schemas() if offer_tools else None,
        on_text=on_text,
        max_tokens=max_tokens,
    )


async def _run_tool(call: ToolCall) -> toolkit.Execution:
    try:
        arguments = call.parsed_arguments()
    except ValueError as exc:
        return toolkit.Execution(
            name=call.name,
            arguments={},
            ok=False,
            result=None,
            error=str(exc),
            duration_ms=0,
            cached=False,
        )
    return await toolkit.execute(call.name, arguments)


def _drop_duplicates(calls: list[ToolCall]) -> list[ToolCall]:
    """Collapse calls a turn asked for twice with identical arguments.

    Models sometimes emit the same call two or three times in one turn.
    The result cache makes the repeat cheap, but it still spends
    tool budget, clutters the activity trail the user reads, and pads the
    conversation with duplicate tool messages that are re-sent on every
    subsequent turn. Arguments are compared as sent, so the same tool with
    different arguments (three FireSmart zones, two forecast horizons) is
    correctly kept.
    """
    seen: set[tuple[str, str]] = set()
    kept: list[ToolCall] = []
    for call in calls:
        key = (call.name, call.arguments.strip())
        if key in seen:
            log.info("assistant.tool.duplicate_dropped", tool=call.name)
            continue
        seen.add(key)
        kept.append(call)
    return kept


def _assistant_tool_message(text: str, calls: list[ToolCall]) -> dict[str, Any]:
    """Rebuild the assistant turn the way the API expects it echoed back."""
    return {
        "role": "assistant",
        "content": text or None,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments or "{}"},
            }
            for call in calls
        ],
    }


def _record_source(sources: list[dict[str, Any]], name: str, as_of: str | None) -> None:
    for existing in sources:
        if existing["source"] == name:
            return
    sources.append({"source": name, "as_of": as_of})


def _summarise(execution: toolkit.Execution) -> str:
    """One line about a tool result, for the activity trail.

    The full payload already went to the model; the user needs to know what
    happened, not to read the JSON again.
    """
    if not execution.ok:
        return execution.error or "failed"
    result = execution.result
    if result is None:
        return "no data"
    data = result.data
    if isinstance(data, dict):
        for key in (
            "matched",
            "matched_fires",
            "detections",
            "active_zones",
            "status",
            "jobs_reported",
        ):
            if key in data:
                return f"{key.replace('_', ' ')}: {data[key]}"
        if "regions" in data and isinstance(data["regions"], list):
            return f"{len(data['regions'])} regions"
        return ", ".join(list(data)[:4])
    if isinstance(data, list):
        return f"{len(data)} rows"
    return str(data)[:120]


# ─── Non-streaming convenience ───────────────────────────────────────


async def answer(
    request: ChatRequest,
    *,
    settings: Settings | None = None,
    client: OpenRouterClient | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Collect a whole run into one JSON body.

    Used by `?stream=false`, which exists so the endpoint can be exercised
    with a single curl — and so tests do not have to parse SSE to assert on
    behaviour.
    """
    collected: dict[str, Any] = {
        "text": "",
        "tool_calls": [],
        "effects": [],
        "sources": [],
        "suggestions": [],
        "usage": {},
        "safety_notice": None,
        "error": None,
    }
    async for event in run_conversation(request, settings=settings, client=client, api_key=api_key):
        match event.name:
            case "done":
                collected["text"] = event.data.get("text", "")
            case "tool_result":
                collected["tool_calls"].append(
                    {
                        k: event.data.get(k)
                        for k in ("name", "ok", "summary", "duration_ms", "cached")
                    }
                )
            case "effect":
                collected["effects"].append(event.data)
            case "sources":
                collected["sources"] = event.data.get("sources", [])
            case "suggestions":
                collected["suggestions"] = event.data.get("items", [])
            case "usage":
                collected["usage"] = event.data
            case "safety":
                collected["safety_notice"] = event.data.get("message")
            case "error":
                collected["error"] = event.data.get("message")
    return collected


def event_to_sse(event: Event) -> str:
    """Render an event as one SSE frame."""
    return f"event: {event.name}\ndata: {json.dumps(event.data, default=str)}\n\n"


def event_as_dict(event: Event) -> dict[str, Any]:
    return asdict(event)
