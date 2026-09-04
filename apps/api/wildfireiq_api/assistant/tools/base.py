"""Tool registry: declaration, validation, caching, and execution.

A tool is a plain function plus a JSON Schema. The schema is what the model
sees; the function is what runs. Keeping both in one decorator means they
cannot drift apart, which is the usual way a tool-using agent starts lying
about its own capabilities.

Three properties every tool here holds to:

* **It reads, it never writes.** Nothing in this package mutates parquet,
  the database, or an upstream service. The worst a confused model can do
  is ask an expensive question.
* **It carries provenance.** Every result names its source and the moment
  the underlying data was captured, so the answer can cite rather than
  assert.
* **It is bounded.** Results are truncated to a token budget before they
  reach the model. An unbounded `fires_historical` would be 96,356 rows.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger(__name__)

#: Hard ceiling on the JSON a single tool may hand back to the model.
#: ~2,000 tokens. Generous for a summary, ruinous for a raw table — which
#: is the point: tools are expected to aggregate, not to dump.
MAX_RESULT_CHARS = 8000


@dataclass(slots=True)
class ToolResult:
    """What a tool hands back.

    `data` is the payload the model reads. `source` and `as_of` become the
    citation the UI renders. `effects` are instructions for the frontend
    (fly the camera, toggle a layer) that never reach the model.
    """

    data: Any
    source: str = "WildfireIQ"
    as_of: str | None = None
    note: str | None = None
    effects: list[dict[str, Any]] = field(default_factory=list)

    def for_model(self) -> str:
        """Serialise for the tool-result message, truncating if oversized."""
        payload: dict[str, Any] = {"data": self.data, "source": self.source}
        if self.as_of:
            payload["as_of"] = self.as_of
        if self.note:
            payload["note"] = self.note
        text = json.dumps(payload, default=str, ensure_ascii=False)
        if len(text) <= MAX_RESULT_CHARS:
            return text
        # Truncating the JSON string would hand the model malformed input.
        # Replacing the payload keeps it valid and says what happened.
        return json.dumps(
            {
                "source": self.source,
                "as_of": self.as_of,
                "error": (
                    "result too large to return in full "
                    f"({len(text)} chars, limit {MAX_RESULT_CHARS}). "
                    "Re-call this tool with a narrower filter or a smaller limit."
                ),
            },
            default=str,
        )


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]
    ttl_s: float = 60.0
    tags: tuple[str, ...] = ()

    def schema(self) -> dict[str, Any]:
        """The OpenAI/OpenRouter `tools[]` entry for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


REGISTRY: dict[str, ToolSpec] = {}


def tool(
    *,
    name: str,
    description: str,
    parameters: dict[str, Any] | None = None,
    ttl_s: float = 60.0,
    tags: tuple[str, ...] = (),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a function as a model-callable tool."""

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        if name in REGISTRY:
            raise ValueError(f"duplicate tool name: {name}")
        schema = parameters or {"type": "object", "properties": {}}
        schema.setdefault("additionalProperties", False)
        REGISTRY[name] = ToolSpec(
            name=name,
            description=description.strip(),
            parameters=schema,
            fn=fn,
            ttl_s=ttl_s,
            tags=tags,
        )
        return fn

    return decorate


def schemas(exclude: set[str] | None = None) -> list[dict[str, Any]]:
    """Tool schemas to advertise, in a stable order."""
    skip = exclude or set()
    return [spec.schema() for name, spec in sorted(REGISTRY.items()) if name not in skip]


# ─── Argument checking ───────────────────────────────────────────────


class ToolArgumentError(ValueError):
    """Arguments the tool cannot run with. Reported back to the model."""


def validate_arguments(spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
    """Check required keys and coerce scalars to their declared types.

    This is not a full JSON Schema validator — it covers the shapes these
    tools actually declare (flat objects of scalars and string arrays).
    Its real job is turning the model's frequent `"7"` for an integer into
    `7` instead of a TypeError three frames deeper.
    """
    props: dict[str, Any] = spec.parameters.get("properties", {}) or {}
    required: list[str] = spec.parameters.get("required", []) or []

    missing = [key for key in required if args.get(key) is None]
    if missing:
        raise ToolArgumentError(f"missing required argument(s): {', '.join(missing)}")

    cleaned: dict[str, Any] = {}
    for key, value in args.items():
        if key not in props:
            continue  # models occasionally invent a field; ignore it
        if value is None:
            continue
        declared = props[key].get("type")
        try:
            cleaned[key] = _coerce(value, declared)
        except (TypeError, ValueError) as exc:
            raise ToolArgumentError(f"argument {key!r} should be {declared}: {exc}") from exc
    return cleaned


def _coerce(value: Any, declared: str | None) -> Any:
    if declared == "integer":
        return int(float(value)) if not isinstance(value, bool) else int(value)
    if declared == "number":
        return float(value)
    if declared == "boolean":
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "y"}
        return bool(value)
    if declared == "string":
        return str(value)
    if declared == "array":
        if isinstance(value, str):
            # "pets,sensitive" is a common model shortcut for a list.
            return [part.strip() for part in value.split(",") if part.strip()]
        return list(value)
    return value


# ─── Caching ─────────────────────────────────────────────────────────
#
# Tool bodies read parquet off disk and, for the risk grid, run LightGBM.
# Within one conversation the same question often gets asked twice — once
# to answer, once to compare — and across concurrent users the answers are
# identical anyway, because the data only moves when an ingest job runs.

_cache: dict[str, tuple[float, ToolResult]] = {}
_CACHE_MAX_ENTRIES = 256


def _cache_key(name: str, args: dict[str, Any]) -> str:
    return f"{name}:{json.dumps(args, sort_keys=True, default=str)}"


def clear_cache() -> None:
    """Drop every memoised tool result. Used by tests."""
    _cache.clear()


@dataclass(slots=True)
class Execution:
    """One tool invocation and what came of it."""

    name: str
    arguments: dict[str, Any]
    ok: bool
    result: ToolResult | None
    error: str | None
    duration_ms: int
    cached: bool

    def content_for_model(self) -> str:
        if self.ok and self.result is not None:
            return self.result.for_model()
        return json.dumps({"error": self.error or "tool failed"})


async def execute(name: str, args: dict[str, Any]) -> Execution:
    """Run one tool. Never raises — failures come back as `ok=False`.

    A tool error is information the model can act on ("that place is not in
    the gazetteer, ask the user which one they meant"), so it is returned
    to the conversation rather than aborting the run.
    """
    started = time.perf_counter()

    spec = REGISTRY.get(name)
    if spec is None:
        return Execution(
            name=name,
            arguments=args,
            ok=False,
            result=None,
            error=f"unknown tool {name!r}; available: {', '.join(sorted(REGISTRY))}",
            duration_ms=0,
            cached=False,
        )

    try:
        cleaned = validate_arguments(spec, args)
    except ToolArgumentError as exc:
        return Execution(name, args, False, None, str(exc), 0, False)

    key = _cache_key(name, cleaned)
    if spec.ttl_s > 0 and (entry := _cache.get(key)):
        expires_at, cached_result = entry
        if expires_at > time.monotonic():
            return Execution(
                name=name,
                arguments=cleaned,
                ok=True,
                result=cached_result,
                error=None,
                duration_ms=int((time.perf_counter() - started) * 1000),
                cached=True,
            )
        del _cache[key]

    try:
        if inspect.iscoroutinefunction(spec.fn):
            result = await spec.fn(**cleaned)
        else:
            # Tool bodies read parquet and run LightGBM; both block. Off the
            # event loop they go, or one question stalls every other request.
            result = await asyncio.to_thread(lambda: spec.fn(**cleaned))
    except ToolArgumentError as exc:
        # Not a fault: the model asked for something the tool can describe
        # back to it ("that place is not in the gazetteer, here are four
        # that are"). No stack trace, because nothing is broken.
        log.info("assistant.tool.rejected_arguments", tool=name, reason=str(exc))
        return Execution(name, cleaned, False, None, str(exc), 0, False)
    except Exception as exc:
        log.warning("assistant.tool.failed", tool=name, error=str(exc), exc_info=True)
        return Execution(
            name=name,
            arguments=cleaned,
            ok=False,
            result=None,
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=int((time.perf_counter() - started) * 1000),
            cached=False,
        )

    if not isinstance(result, ToolResult):
        result = ToolResult(data=result)

    if spec.ttl_s > 0:
        if len(_cache) >= _CACHE_MAX_ENTRIES:
            _cache.clear()  # crude, but the entries are cheap to rebuild
        _cache[key] = (time.monotonic() + spec.ttl_s, result)

    return Execution(
        name=name,
        arguments=cleaned,
        ok=True,
        result=result,
        error=None,
        duration_ms=int((time.perf_counter() - started) * 1000),
        cached=False,
    )


# ─── Shared helpers for tool bodies ──────────────────────────────────


def newest_timestamp(rows: list[dict[str, Any]], *fields: str) -> str | None:
    """Latest non-empty value across the given timestamp columns."""
    best: str | None = None
    for row in rows:
        for name in fields:
            value = row.get(name)
            if value is None:
                continue
            text = str(value)
            if best is None or text > best:
                best = text
    return best


def round_floats(value: Any, places: int = 2) -> Any:
    """Recursively round floats. Full float64 precision in a tool result is
    noise the model pays for by the token and cannot use."""
    if isinstance(value, float):
        return None if value != value else round(value, places)  # NaN → None
    if isinstance(value, dict):
        return {k: round_floats(v, places) for k, v in value.items()}
    if isinstance(value, list):
        return [round_floats(v, places) for v in value]
    return value
