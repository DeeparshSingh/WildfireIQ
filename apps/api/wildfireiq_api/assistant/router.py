"""HTTP surface for the assistant.

`POST /api/assistant/chat` streams Server-Sent Events by default. The
frames are the harness's own events verbatim, so anything the agent can
report, the browser can render — including tool activity and map effects,
which arrive while the answer is still being written.

Passing `?stream=false` returns the whole run as one JSON body instead.
That exists so the endpoint is testable with a single curl and so the
frontend has a fallback if a proxy mangles SSE.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..settings import get_settings
from . import tools as toolkit
from .brief import brief_metadata, build_brief
from .harness import ChatRequest, answer, availability, event_to_sse, run_conversation
from .prompts import STARTER_PROMPTS

router = APIRouter()


class ChatMessage(BaseModel):
    """One transcript turn. Only the two roles the client is allowed to send.

    The system prompt is never accepted from a request — it is rebuilt
    server-side every time, so a crafted `system` turn cannot reach the
    model with the authority of one.
    """

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=6000)


class UserContext(BaseModel):
    """What the browser knows about the user's current view.

    Every field is optional: the assistant works with none of it, just
    less precisely. Nothing here is stored — it lives for the length of
    one request, the same way the rest of this backend holds no PII.
    """

    page: str | None = None
    lat: float | None = None
    lon: float | None = None
    place_label: str | None = None
    dwelling: str | None = None
    situation: list[str] | None = None
    visible_layers: list[str] | None = None


class ChatBody(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    context: UserContext | None = None


def _require_available() -> None:
    state = availability()
    if not state["enabled"]:
        raise HTTPException(503, "The assistant is disabled on this deployment.")
    if not state["configured"]:
        raise HTTPException(
            503,
            "The assistant has no OpenRouter API key. Set OPENROUTER_API_KEY in .env.",
        )


@router.get("/health", summary="Whether the assistant is configured and what it can do")
async def health() -> dict[str, Any]:
    return {**availability(), "brief": brief_metadata()}


@router.get("/tools", summary="The assistant's toolset")
async def list_tools() -> dict[str, Any]:
    return {
        "count": len(toolkit.REGISTRY),
        "tools": toolkit.catalogue(),
        "starter_prompts": list(STARTER_PROMPTS),
    }


@router.get("/brief", summary="The live situation brief the assistant is primed with")
async def brief() -> dict[str, Any]:
    """Exposed because an assistant whose grounding you cannot inspect is
    an assistant you cannot audit."""
    return {"brief": await asyncio.to_thread(build_brief)}


@router.post("/chat", summary="Ask the assistant a question")
async def chat(body: ChatBody, stream: bool = True) -> Any:
    _require_available()
    settings = get_settings()
    request = ChatRequest(
        messages=[m.model_dump() for m in body.messages],
        context=body.context.model_dump(exclude_none=True) if body.context else None,
    )

    if not stream:
        return await answer(request, settings=settings)

    async def frames() -> AsyncIterator[str]:
        async for event in run_conversation(request, settings=settings):
            yield event_to_sse(event)

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            # Nginx buffers SSE into uselessness without this.
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


__all__ = ["ChatBody", "ChatMessage", "UserContext", "router"]
