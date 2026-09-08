"""Personalized FireSmart Hub.

Reads two static reference files (no upstream calls):

  data/firesmart/firesmart_actions.json   — 30 curated HIZ + Plan-&-Go-Bag actions
                                            sourced from FireSmart Canada's
                                            Home Ignition Zone Assessment.
  data/geo/kamloops_neighbourhoods.geojson — 14 Kamloops neighbourhood polygons
                                             for the onboarding selector + inset
                                             fly-to.

Every state-mutating concept (progress, photos, streaks) lives on the client,
which also awards the badges. This router only composes static reference data
with the user's dwelling, season and situation filters. No PII ever touches
the backend.

The achievement catalogue is served here so the client and any future surface
agree on the list; the rules that award them live in the client alone. A second
server-side implementation of those rules existed and was removed in the
September 2026 audit: nothing called it, and two copies of a badge ladder is a
guarantee that one of them eventually drifts.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from . import _data
from ._envelope import Envelope, Meta

router = APIRouter()


REPO_ROOT = Path(__file__).resolve().parents[4]
ACTIONS_PATH = REPO_ROOT / "data" / "firesmart" / "firesmart_actions.json"
NEIGHBOURHOODS_PATH = REPO_ROOT / "data" / "geo" / "kamloops_neighbourhoods.geojson"


@lru_cache(maxsize=1)
def _load_actions() -> dict[str, Any]:
    with ACTIONS_PATH.open() as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _load_neighbourhoods() -> dict[str, Any]:
    with NEIGHBOURHOODS_PATH.open() as f:
        return json.load(f)


# ─── Achievement catalogue (≥ 12) ──────────────────────────────────────
# Definitions are hosted server-side so the frontend and any future surface
# (e.g. a shared progress view) agree on the rules.

ACHIEVEMENTS: list[dict[str, Any]] = [
    {
        "id": "first_steps",
        "label": "First Steps",
        "blurb": "Complete your first FireSmart action.",
        "emoji": "🌱",
        "rule": "completed>=1",
    },
    {
        "id": "ember_aware",
        "label": "Ember-Aware",
        "blurb": "Complete 5 actions across any zones.",
        "emoji": "🪵",
        "rule": "completed>=5",
    },
    {
        "id": "zone_one_hero",
        "label": "Zone 1 Hero",
        "blurb": "Finish every Immediate Zone action that applies to you.",
        "emoji": "🛡️",
        "rule": "all_zone:immediate",
    },
    {
        "id": "defensible_space",
        "label": "Defensible Space",
        "blurb": "Earn 25 points across any zones.",
        "emoji": "🏕️",
        "rule": "points>=25",
    },
    {
        "id": "halfway",
        "label": "Halfway There",
        "blurb": "Tick off 50% of the actions that apply to you.",
        "emoji": "🚧",
        "rule": "completed>=total/2",
    },
    {
        "id": "photo_documentarian",
        "label": "Photo Documentarian",
        "blurb": "Attach photos to 5 completed actions.",
        "emoji": "📷",
        "rule": "photos>=5",
    },
    {
        "id": "smoke_aware",
        "label": "Smoke-Aware",
        "blurb": "Open the AQ guidance during a moderate-or-worse smoke day.",
        "emoji": "💨",
        "rule": "smoke_aware",
    },
    {
        "id": "streak_7",
        "label": "Streak: 7",
        "blurb": "Visit the hub 7 days in a row.",
        "emoji": "🔥",
        "rule": "streak>=7",
    },
    {
        "id": "streak_30",
        "label": "Streak: 30",
        "blurb": "Visit the hub 30 days in a row.",
        "emoji": "🗓️",
        "rule": "streak>=30",
    },
    {
        "id": "storm_ready",
        "label": "Storm Ready",
        "blurb": "Finish your Plan & Go-Bag actions before July 1.",
        "emoji": "🎒",
        "rule": "all_zone:plan_gobag&before_july",
    },
    {
        "id": "neighbour",
        "label": "Neighbour",
        "blurb": "Share your progress link (your data stays in the URL, never on a server).",
        "emoji": "🤝",
        "rule": "shared",
    },
    {
        "id": "firesmart_home",
        "label": "FireSmart Home",
        "blurb": "Complete every action that applies to you.",
        "emoji": "🏆",
        "rule": "completed==total",
    },
]


# ─── Filtering ─────────────────────────────────────────────────────────


def _filter_actions(
    dwelling: str,
    season: str,
    situation: list[str],
) -> list[dict[str, Any]]:
    """Apply dwelling + situation gating; sort by season relevance."""
    raw = _load_actions()["actions"]
    d = dwelling.lower()
    s = season.lower()
    sit = {x.lower() for x in situation}

    out: list[dict[str, Any]] = []
    for a in raw:
        applies = a.get("applies", {})

        # Dwelling gate — required.
        dwellings = applies.get("dwelling", [])
        if dwellings and d not in dwellings:
            continue

        # Situation gate — if the action has a "situation" list, the user
        # must have *at least one* of those tags. Actions without a
        # situation field apply universally.
        required = applies.get("situation")
        if required and not (sit & set(required)):
            continue

        out.append(a)

    # Season-aware ordering: highest season_priority first, then by points.
    def _key(a: dict[str, Any]) -> tuple[int, int]:
        sp = a.get("season_priority") or {}
        return (-int(sp.get(s, 3)), -int(a.get("points", 0)))

    out.sort(key=_key)
    return out


# ─── Endpoints ─────────────────────────────────────────────────────────


@router.get("/checklist", summary="Personalised HIZ + Plan-&-Go-Bag checklist")
async def checklist(
    dwelling: str = "house",
    season: str = "summer",
    situation: str = "",
) -> dict[str, Any]:
    """Return groups + filtered, season-ordered actions for the user's situation.

    `situation` is a comma-separated list: e.g. "pets,sensitive,outdoor_worker".
    """
    sit = [s.strip() for s in situation.split(",") if s.strip()]
    actions = _filter_actions(dwelling, season, sit)
    groups = _load_actions()["_groups"]
    return Envelope[dict](
        data={
            "groups": groups,
            "actions": actions,
            "max_points": sum(a["points"] for a in actions),
            "version": _load_actions()["_version"],
        },
        meta=Meta(
            source="firesmart_canada",
            attribution="FireSmart Canada — Home Ignition Zone Assessment",
        ),
    ).model_dump(mode="json")


@router.get("/neighbourhoods", summary="Kamloops neighbourhood polygons")
async def neighbourhoods() -> dict[str, Any]:
    fc = _load_neighbourhoods()
    return Envelope[dict](
        data=fc,
        meta=Meta(
            source="kamloops_open_data",
            attribution="WildfireIQ — curated from City of Kamloops neighbourhood descriptions",
        ),
    ).model_dump(mode="json")


@router.get("/achievements", summary="Achievement catalogue (12 badges)")
async def achievements() -> dict[str, Any]:
    return Envelope[dict](
        data={"achievements": ACHIEVEMENTS},
        meta=Meta(
            source="firesmart_canada",
            attribution="WildfireIQ",
        ),
    ).model_dump(mode="json")


@router.get("/season-context", summary="Days-since-rain + season-peak countdown")
async def season_context() -> dict[str, Any]:
    ctx = _data.season_context()
    return Envelope[dict](
        data=ctx,
        meta=Meta(
            source="wildfireiq_derived",
            attribution="Open-Meteo daily wx + BC Wildfire Service historical fires",
        ),
    ).model_dump(mode="json")
