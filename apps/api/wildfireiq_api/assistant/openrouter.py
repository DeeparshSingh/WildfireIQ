"""Streaming transport for OpenRouter's chat-completions API.

OpenRouter speaks the OpenAI wire format, so this is a thin client rather
than an SDK wrapper: one dependency less, and the streaming tool-call
assembly is the only part with real subtlety anyway.

That subtlety: a tool call does not arrive whole. It arrives as a run of
deltas that each carry a slice of the JSON argument string, keyed by an
`index` that identifies which of several parallel calls the slice belongs
to. `_ToolCallAccumulator` stitches those back together.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

API_URL = "https://openrouter.ai/api/v1/chat/completions"

log = structlog.get_logger(__name__)


class OpenRouterError(RuntimeError):
    """Any non-recoverable failure talking to OpenRouter.

    The message is written for the person who will read it in the chat
    panel. The upstream detail goes to the log instead — it is diagnostic,
    it can echo request internals, and "HTTP 401: {"error":{"message":
    "Missing Authentication header"...}}" tells a user nothing they can act
    on.
    """


#: What each upstream status actually means for whoever is asking.
_STATUS_MESSAGES: dict[int, str] = {
    401: "The assistant's API key was rejected. Check OPENROUTER_API_KEY in .env.",
    402: "The assistant's OpenRouter account is out of credit.",
    403: "OpenRouter refused this request — the key may not have access to this model.",
    408: "The model took too long to respond. Try again.",
    429: "The assistant is being rate-limited upstream. Wait a moment and try again.",
    502: "OpenRouter could not reach the model provider. Try again shortly.",
    503: "The model is temporarily unavailable upstream. Try again shortly.",
}


def _describe_failure(status: int, body: str) -> OpenRouterError:
    """Turn an upstream failure into something worth showing a user."""
    log.warning("assistant.openrouter.http_error", status=status, body=body[:400])
    friendly = _STATUS_MESSAGES.get(status)
    if friendly:
        return OpenRouterError(friendly)
    if 500 <= status < 600:
        return OpenRouterError("The model provider is having trouble. Try again shortly.")
    # Unmapped 4xx: the upstream message is the only useful signal, and at
    # this point it is more likely to help than to confuse.
    detail = body.strip()
    try:
        parsed = json.loads(detail)
        detail = str((parsed.get("error") or {}).get("message") or detail)
    except (json.JSONDecodeError, AttributeError):
        pass
    return OpenRouterError(f"The assistant could not reach the model ({status}): {detail[:200]}")


@dataclass(slots=True)
class ToolCall:
    """One function call requested by the model."""

    id: str
    name: str
    arguments: str  # raw JSON text; may be malformed if the model slipped

    def parsed_arguments(self) -> dict[str, Any]:
        """Decode `arguments`, tolerating an empty or malformed payload.

        A model that calls a zero-argument tool often sends `""` rather than
        `"{}"`, and one that truncates mid-JSON should produce a tool error
        the model can read and retry from, not a 500.
        """
        if not self.arguments.strip():
            return {}
        try:
            value = json.loads(self.arguments)
        except json.JSONDecodeError as exc:
            raise ValueError(f"arguments were not valid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError("arguments must be a JSON object")
        return value


@dataclass(slots=True)
class Usage:
    """Token counts and cost for one model turn."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
        )


@dataclass(slots=True)
class StepResult:
    """Everything one model turn produced.

    `reasoning_chars` counts the model's private thinking channel. It is
    never shown and never fed back, but it is billed as output and it
    shares the `max_tokens` budget with the answer — so when a turn comes
    back empty, this is the number that explains why.
    """

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    usage: Usage = field(default_factory=Usage)
    reasoning_chars: int = 0

    @property
    def truncated(self) -> bool:
        """The turn ran out of output budget before it finished."""
        return self.finish_reason == "length"


class _ToolCallAccumulator:
    """Reassemble streamed tool-call fragments into whole calls.

    Fragments are keyed by `index`. Some providers omit it, in which case a
    fragment that carries an `id` starts a new call and one that does not
    continues the call already in progress — which is what a provider
    streaming calls sequentially means by leaving the index out.
    """

    def __init__(self) -> None:
        self._by_index: dict[int, dict[str, str]] = {}
        self._last_index: int | None = None

    def add(self, fragments: list[dict[str, Any]]) -> None:
        for frag in fragments:
            idx = frag.get("index")
            if not isinstance(idx, int):
                if frag.get("id") or self._last_index is None:
                    idx = len(self._by_index)
                else:
                    idx = self._last_index
            self._last_index = idx
            slot = self._by_index.setdefault(idx, {"id": "", "name": "", "arguments": ""})
            if frag.get("id"):
                slot["id"] = str(frag["id"])
            fn = frag.get("function") or {}
            if fn.get("name"):
                slot["name"] = str(fn["name"])
            if fn.get("arguments"):
                slot["arguments"] += str(fn["arguments"])

    def finish(self) -> list[ToolCall]:
        out: list[ToolCall] = []
        for idx in sorted(self._by_index):
            slot = self._by_index[idx]
            if not slot["name"]:
                continue  # a fragment run that never named a function
            out.append(
                ToolCall(
                    # A synthetic id keeps the tool-result messages valid even
                    # if the provider never sent one.
                    id=slot["id"] or f"call_{idx}",
                    name=slot["name"],
                    arguments=slot["arguments"],
                )
            )
        return out


def _parse_usage(raw: dict[str, Any] | None) -> Usage:
    if not raw:
        return Usage()
    return Usage(
        prompt_tokens=int(raw.get("prompt_tokens") or 0),
        completion_tokens=int(raw.get("completion_tokens") or 0),
        # `cost` is an OpenRouter extension, present when the request asked
        # for usage accounting. It is the real charge in USD credits.
        cost_usd=float(raw.get("cost") or 0.0),
    )


class OpenRouterClient:
    """One conversation's worth of OpenRouter calls.

    Holds no state between calls beyond the HTTP client, so a single
    instance is safe to reuse across steps of the same agent run.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        referer: str = "",
        title: str = "",
        timeout_s: float = 90.0,
        reasoning_effort: str | None = None,
    ) -> None:
        if not api_key:
            raise OpenRouterError("OPENROUTER_API_KEY is not set")
        self.model = model
        self.reasoning_effort = reasoning_effort
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title
        # Generous read timeout: a long tool-planning turn can pause between
        # tokens. The connect timeout stays short so a dead network fails fast.
        self._timeout = httpx.Timeout(timeout_s, connect=10.0)
        self._headers = headers

    def _body(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        *,
        stream: bool,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            "max_tokens": max_tokens,
            # Ask OpenRouter to report the actual credit cost of the call so
            # the harness can surface a real number rather than an estimate.
            "usage": {"include": True},
        }
        if self.reasoning_effort:
            # OpenRouter reserves the reasoning allowance before the answer
            # is written, so capping effort protects the answer as well as
            # the clock. Models that do not reason ignore this.
            body["reasoning"] = {"effort": self.reasoning_effort}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        return body

    async def stream_step(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        on_text: Callable[[str], Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 3000,
    ) -> StepResult:
        """Run one model turn, streaming text deltas to `on_text`.

        Returns once the turn finishes, with any tool calls reassembled.
        `on_text` may be sync or async; it is awaited when it returns an
        awaitable so the caller can push straight into an SSE queue.
        """
        result = StepResult()
        acc = _ToolCallAccumulator()
        body = self._body(
            messages, tools, stream=True, temperature=temperature, max_tokens=max_tokens
        )

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream("POST", API_URL, headers=self._headers, json=body) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", "replace")
                    raise _describe_failure(response.status_code, body)

                async for line in response.aiter_lines():
                    chunk = _decode_sse_line(line)
                    if chunk is _DONE:
                        break
                    if chunk is None:
                        continue

                    # A mid-stream error arrives inside a 200 response,
                    # because the headers went out before anything failed.
                    if err := chunk.get("error"):
                        raise OpenRouterError(str(err.get("message") or err))

                    if usage := chunk.get("usage"):
                        result.usage = _parse_usage(usage)

                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if text := delta.get("content"):
                            result.text += text
                            if on_text is not None:
                                maybe = on_text(text)
                                if hasattr(maybe, "__await__"):
                                    await maybe
                        if reasoning := delta.get("reasoning"):
                            result.reasoning_chars += len(str(reasoning))
                        if frags := delta.get("tool_calls"):
                            acc.add(frags)
                        if reason := choice.get("finish_reason"):
                            result.finish_reason = reason

        result.tool_calls = acc.finish()
        return result

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> StepResult:
        """Non-streaming, no-tools turn. Used for short auxiliary calls."""
        body = self._body(
            messages, None, stream=False, temperature=temperature, max_tokens=max_tokens
        )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(API_URL, headers=self._headers, json=body)
            if response.status_code >= 400:
                raise _describe_failure(response.status_code, response.text)
            payload = response.json()

        if err := payload.get("error"):
            raise OpenRouterError(str(err.get("message") or err))
        choices = payload.get("choices") or []
        message = (choices[0].get("message") if choices else None) or {}
        return StepResult(
            text=message.get("content") or "",
            finish_reason=(choices[0].get("finish_reason") if choices else None),
            usage=_parse_usage(payload.get("usage")),
        )


# ─── SSE decoding ────────────────────────────────────────────────────

_DONE = object()


def _decode_sse_line(line: str) -> dict[str, Any] | object | None:
    """Turn one SSE line into a chunk, the DONE sentinel, or None to skip.

    OpenRouter interleaves `: OPENROUTER PROCESSING` keepalive comments with
    the data frames. Per the SSE spec any line starting with `:` is a
    comment, so skipping them before JSON parsing is not a special case —
    it is just reading SSE correctly.
    """
    if not line or line.startswith(":"):
        return None
    if not line.startswith("data:"):
        return None
    payload = line[len("data:") :].strip()
    if not payload:
        return None
    if payload == "[DONE]":
        return _DONE
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        log.warning("assistant.sse.undecodable_chunk", preview=payload[:120])
        return None


async def iter_sse_chunks(lines: AsyncIterator[str]) -> AsyncIterator[dict[str, Any]]:
    """Decode an SSE line stream into chunks. Exposed for tests."""
    async for line in lines:
        chunk = _decode_sse_line(line)
        if chunk is _DONE:
            return
        if chunk is not None:
            yield chunk  # type: ignore[misc]
