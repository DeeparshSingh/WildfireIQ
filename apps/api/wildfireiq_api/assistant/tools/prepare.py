"""FireSmart preparedness tools."""

from __future__ import annotations

from typing import Any

from ...routers import firesmart as firesmart_router
from .base import ToolResult, tool

FIRESMART_SOURCE = "FireSmart Canada — Home Ignition Zone Assessment"

_ZONE_LABELS = {
    "immediate": "Immediate Zone (0-1.5 m from the house)",
    "intermediate_a": "Intermediate Zone A (1.5-10 m)",
    "intermediate_b": "Intermediate Zone B (10-30 m)",
    "extended": "Extended Zone (30-100 m)",
    "plan_gobag": "Emergency plan and go-bag",
}


@tool(
    name="get_firesmart_actions",
    description=(
        "Personalised FireSmart home-hardening and go-bag actions, filtered by "
        "dwelling type and circumstances and ordered by how urgent each one is "
        "in the given season. Each action carries why it matters, a time "
        "estimate, and a cost band. Use for 'how do I protect my house', "
        "'what should I do this weekend', 'what goes in a go-bag'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "dwelling": {
                "type": "string",
                "enum": ["house", "townhouse", "apartment", "mobile", "cabin"],
                "description": "Dwelling type. Default 'house'.",
            },
            "season": {
                "type": "string",
                "enum": ["spring", "summer", "fall", "winter"],
                "description": "Season to prioritise for. Default 'summer'.",
            },
            "situation": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Circumstances that unlock extra actions: pets, sensitive "
                    "(respiratory or cardiac), outdoor_worker, mobility, children, "
                    "renter, acreage."
                ),
            },
            "zone": {
                "type": "string",
                "enum": list(_ZONE_LABELS),
                "description": "Return only one zone's actions.",
            },
            "limit": {
                "type": "integer",
                "description": "Max actions to return (max 20). Default 8.",
            },
        },
    },
    ttl_s=3600,
    tags=("prepare",),
)
async def get_firesmart_actions(
    dwelling: str = "house",
    season: str = "summer",
    situation: list[str] | None = None,
    zone: str | None = None,
    limit: int = 8,
) -> ToolResult:
    # Through the router, so the assistant's list is the same list the
    # preparedness hub renders — including the dwelling and situation gating.
    envelope = await firesmart_router.checklist(
        dwelling=dwelling,
        season=season,
        situation=",".join(situation or []),
    )
    payload: dict[str, Any] = envelope["data"]

    actions = payload["actions"]
    if zone:
        actions = [a for a in actions if a["zone"] == zone]
    limit = max(1, min(int(limit), 20))

    return ToolResult(
        data={
            "profile": {"dwelling": dwelling, "season": season, "situation": situation or []},
            "actions_available": len(payload["actions"]),
            "zones": _ZONE_LABELS,
            "actions": [
                {
                    "id": a["id"],
                    "zone": a["zone"],
                    "title": a["title"],
                    "why": a["why"],
                    "minutes": a.get("estimated_minutes"),
                    "cost": a.get("cost"),
                    "points": a.get("points"),
                }
                for a in actions[:limit]
            ],
            "ordering": (
                f"Highest {season} priority first. The Immediate Zone matters most: "
                "most homes lost to wildfire are ignited by embers landing on or "
                "beside the structure, not by the flame front itself."
            ),
        },
        source=FIRESMART_SOURCE,
        note="The user can tick these off and track progress on the Prepare page.",
    )
