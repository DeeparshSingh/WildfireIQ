"""Standard `{data, meta}` response envelope used by every router."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Meta(BaseModel):
    cached_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "wildfireiq"
    attribution: str = ""
    phase: str = "0"
    note: str | None = None


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: Meta


def not_implemented(name: str, target_phase: str) -> dict[str, Any]:
    return Envelope[dict](
        data={},
        meta=Meta(
            source=name,
            attribution="",
            phase="0",
            note=f"Endpoint stub. Implementation planned for Phase {target_phase}.",
        ),
    ).model_dump(mode="json")
