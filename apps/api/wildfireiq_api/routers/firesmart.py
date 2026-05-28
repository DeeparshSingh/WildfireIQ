"""Personalized FireSmart Hub (Phase 5).

Reads two static reference files (no upstream calls):

  data/firesmart/firesmart_actions.json   — 30 curated HIZ + Plan-&-Go-Bag actions
                                            sourced from FireSmart Canada's
                                            Home Ignition Zone Assessment.
  data/geo/kamloops_neighbourhoods.geojson — 14 Kamloops neighbourhood polygons
                                             for the onboarding selector + inset
                                             fly-to.

Every state-mutating concept (progress, photos, streaks) lives on the client.
This router just composes static reference data with situation / season /
dwelling filters, then serves a stateless badge-ladder oracle. No PII ever
touches the backend.
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
    {"id": "first_steps", "label": "First Steps", "blurb": "Complete your first FireSmart action.", "emoji": "🌱", "rule": "completed>=1"},
    {"id": "ember_aware", "label": "Ember-Aware", "blurb": "Complete 5 actions across any zones.", "emoji": "🪵", "rule": "completed>=5"},
    {"id": "zone_one_hero", "label": "Zone 1 Hero", "blurb": "Finish every Immediate Zone action that applies to you.", "emoji": "🛡️", "rule": "all_zone:immediate"},
    {"id": "defensible_space", "label": "Defensible Space", "blurb": "Earn 25 points across any zones.", "emoji": "🏕️", "rule": "points>=25"},
    {"id": "halfway", "label": "Halfway There", "blurb": "Tick off 50% of the actions that apply to you.", "emoji": "🚧", "rule": "completed>=total/2"},
    {"id": "photo_documentarian", "label": "Photo Documentarian", "blurb": "Attach photos to 5 completed actions.", "emoji": "📷", "rule": "photos>=5"},
    {"id": "smoke_aware", "label": "Smoke-Aware", "blurb": "Open the AQ guidance during a moderate-or-worse smoke day.", "emoji": "💨", "rule": "smoke_aware"},
    {"id": "streak_7", "label": "Streak: 7", "blurb": "Visit the hub 7 days in a row.", "emoji": "🔥", "rule": "streak>=7"},
    {"id": "streak_30", "label": "Streak: 30", "blurb": "Visit the hub 30 days in a row.", "emoji": "🗓️", "rule": "streak>=30"},
    {"id": "storm_ready", "label": "Storm Ready", "blurb": "Finish your Plan & Go-Bag actions before July 1.", "emoji": "🎒", "rule": "all_zone:plan_gobag&before_july"},
    {"id": "neighbour", "label": "Neighbour", "blurb": "Share your progress link (your data stays in the URL, never on a server).", "emoji": "🤝", "rule": "shared"},
    {"id": "firesmart_home", "label": "FireSmart Home", "blurb": "Complete every action that applies to you.", "emoji": "🏆", "rule": "completed==total"},
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


def _badges_for(
    points: int,
    completed: int,
    total: int,
    photos: int,
    streak: int,
    completed_ids: set[str],
    actions: list[dict[str, Any]],
    flags: dict[str, bool],
    today_iso: str | None,
) -> list[dict[str, str]]:
    """Centralised badge ladder. Mirrors the frontend exactly."""
    earned: list[dict[str, str]] = []

    def _has(pred: bool, ach_id: str) -> None:
        if not pred:
            return
        for a in ACHIEVEMENTS:
            if a["id"] == ach_id:
                earned.append({"id": a["id"], "label": a["label"], "emoji": a["emoji"], "blurb": a["blurb"]})
                return

    _has(completed >= 1, "first_steps")
    _has(completed >= 5, "ember_aware")
    _has(points >= 25, "defensible_space")
    _has(total > 0 and completed >= total / 2, "halfway")
    _has(photos >= 5, "photo_documentarian")
    _has(flags.get("smoke_aware", False), "smoke_aware")
    _has(streak >= 7, "streak_7")
    _has(streak >= 30, "streak_30")
    _has(flags.get("shared", False), "neighbour")
    _has(total > 0 and completed == total, "firesmart_home")

    # Zone 1 Hero
    zone_1_actions = [a for a in actions if a["zone"] == "immediate"]
    if zone_1_actions and all(a["id"] in completed_ids for a in zone_1_actions):
        _has(True, "zone_one_hero")

    # Storm Ready — plan_gobag complete before July 1
    pg_actions = [a for a in actions if a["zone"] == "plan_gobag"]
    before_july = today_iso is not None and today_iso[5:7] in {"01", "02", "03", "04", "05", "06"}
    if pg_actions and all(a["id"] in completed_ids for a in pg_actions) and before_july:
        _has(True, "storm_ready")

    return earned


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
            phase="5",
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
            phase="5",
        ),
    ).model_dump(mode="json")


@router.get("/achievements", summary="Achievement catalogue (12 badges)")
async def achievements() -> dict[str, Any]:
    return Envelope[dict](
        data={"achievements": ACHIEVEMENTS},
        meta=Meta(
            source="firesmart_canada",
            attribution="WildfireIQ — Phase 5",
            phase="5",
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
            phase="5",
        ),
    ).model_dump(mode="json")


@router.post("/score", summary="Compute points + badges from a completed-items list")
async def score(payload: dict[str, Any]) -> dict[str, Any]:
    """Stateless oracle so client + server agree on the badge ladder.

    Body shape:
      {
        completed_ids: [...],
        dwelling, season, situation: [...],
        photos: int, streak: int,
        flags: {smoke_aware: bool, shared: bool},
        today: "YYYY-MM-DD"
      }
    """
    completed_ids = set(payload.get("completed_ids", []) or [])
    dwelling = (payload.get("dwelling") or "house").lower()
    season = (payload.get("season") or "summer").lower()
    situation = [s.lower() for s in (payload.get("situation") or [])]
    photos = int(payload.get("photos") or 0)
    streak = int(payload.get("streak") or 0)
    flags = payload.get("flags") or {}
    today = payload.get("today")

    actions = _filter_actions(dwelling, season, situation)
    total = len(actions)
    completed = sum(1 for a in actions if a["id"] in completed_ids)
    points = sum(a["points"] for a in actions if a["id"] in completed_ids)
    max_points = sum(a["points"] for a in actions)

    badges = _badges_for(
        points=points,
        completed=completed,
        total=total,
        photos=photos,
        streak=streak,
        completed_ids=completed_ids,
        actions=actions,
        flags=flags,
        today_iso=today,
    )

    return Envelope[dict](
        data={
            "points": points,
            "max_points": max_points,
            "completed": completed,
            "total": total,
            "badges": badges,
            "all_achievements": ACHIEVEMENTS,
        },
        meta=Meta(
            source="firesmart_canada",
            attribution="FireSmart Canada",
            phase="5",
        ),
    ).model_dump(mode="json")
