"""The assistant's toolset.

Importing this package registers every tool. Import order is irrelevant —
each module registers under its own names and `base.tool` refuses
duplicates — but the modules are listed here so `REGISTRY` is never
half-populated because someone imported `base` directly.
"""

from __future__ import annotations

from . import (  # noqa: F401  (imported for their registration side effects)
    air,
    climate,
    prepare,
    reference,
    situation,
    ui,
    weather,
)
from .base import (
    REGISTRY,
    Execution,
    ToolArgumentError,
    ToolResult,
    ToolSpec,
    clear_cache,
    execute,
    schemas,
)

__all__ = [
    "REGISTRY",
    "Execution",
    "ToolArgumentError",
    "ToolResult",
    "ToolSpec",
    "catalogue",
    "clear_cache",
    "execute",
    "schemas",
]


def catalogue() -> list[dict[str, object]]:
    """Human-readable listing of the toolset, for `/api/assistant/tools`."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "tags": list(spec.tags),
            "parameters": sorted((spec.parameters.get("properties") or {}).keys()),
            "cache_seconds": spec.ttl_s,
        }
        for spec in sorted(REGISTRY.values(), key=lambda s: (s.tags[:1], s.name))
    ]
