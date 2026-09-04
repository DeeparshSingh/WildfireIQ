"""Standard `{data, meta}` response envelope used by every router."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class Meta(BaseModel):
    """Provenance for a response payload.

    `source` names the pipeline that produced the data, `attribution`
    carries the upstream credit the UI renders, and `note` is an optional
    caveat (for example, a placeholder dataset).
    """

    cached_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = "wildfireiq"
    attribution: str = ""
    note: str | None = None


class Envelope[T](BaseModel):
    data: T
    meta: Meta
