"""Personalized FireSmart checklist (Phase 5).

Source of items: FireSmart Canada — "Protecting your Home from Wildfire" /
Home Ignition Zone (HIZ) Assessment workbook. The HIZ is structured as four
concentric zones outward from the structure:

  Immediate Zone   0 – 1.5 m   (non-combustible "ember-defensible" perimeter)
  Intermediate A   1.5 – 10 m  (lean, clean, green — well-spaced low fuels)
  Intermediate B   10 – 30 m   (thinned canopy, ladder fuels removed)
  Extended         30 – 100 m  (selective thinning, surface fuel reduction)

We host a curated checklist here so the frontend can render it without
re-hitting an external server, then filter by user situation (dwelling type,
season). Nothing is written back — all progress lives in the browser's
localStorage. No PII ever touches this backend.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ._envelope import Envelope, Meta

router = APIRouter()


ZONES: list[dict[str, Any]] = [
    {
        "id": "immediate",
        "label": "Immediate Zone",
        "distance": "0 – 1.5 m",
        "blurb": (
            "The 1.5-metre non-combustible band hugging your home. Embers that "
            "land here are the #1 way houses ignite during a wildfire — keep it "
            "clear, period."
        ),
    },
    {
        "id": "intermediate_a",
        "label": "Intermediate Zone · Inner",
        "distance": "1.5 – 10 m",
        "blurb": (
            "Lean, clean, and green. Spaced-out plantings, irrigated lawn, no "
            "ladder fuels under trees, hardscape paths where you can."
        ),
    },
    {
        "id": "intermediate_b",
        "label": "Intermediate Zone · Outer",
        "distance": "10 – 30 m",
        "blurb": (
            "Thin canopies so flames can't crown from tree to tree. Limb to 2 m. "
            "Keep surface fuels low and discontinuous."
        ),
    },
    {
        "id": "extended",
        "label": "Extended Zone",
        "distance": "30 – 100 m",
        "blurb": (
            "Selective thinning reduces the intensity of a fire reaching your "
            "property. Coordinate with neighbours — embers travel kilometres."
        ),
    },
]


# Each item is rated 1–5 points by impact-per-effort per FireSmart Canada guidance.
ITEMS: list[dict[str, Any]] = [
    # ─── Immediate (0–1.5 m) ────────────────────────────────────────────
    {
        "id": "im_roof_debris",
        "zone": "immediate",
        "title": "Clear roof and gutters of needles, leaves, debris",
        "detail": "Dry organic litter is the most common ember-ignition site. Check after every windstorm.",
        "season": "any",
        "applies_to": ["house", "townhome", "cabin", "mobile"],
        "points": 5,
    },
    {
        "id": "im_no_combustibles",
        "zone": "immediate",
        "title": "No combustibles within 1.5 m of the structure",
        "detail": "Move firewood, propane tanks, bark mulch, patio cushions, and recycling bins out of the 1.5 m zone.",
        "season": "any",
        "applies_to": ["house", "townhome", "cabin", "mobile"],
        "points": 5,
    },
    {
        "id": "im_vents_screened",
        "zone": "immediate",
        "title": "Vents covered with 3 mm non-combustible mesh",
        "detail": "Embers enter attics and crawlspaces through unscreened vents. Replace plastic/wood mesh with metal.",
        "season": "any",
        "applies_to": ["house", "cabin", "mobile"],
        "points": 4,
    },
    {
        "id": "im_decks_enclosed",
        "zone": "immediate",
        "title": "Enclose or screen the underside of decks",
        "detail": "Open decks collect embers. Solid skirting (non-combustible) or fine mesh prevents accumulation.",
        "season": "any",
        "applies_to": ["house", "cabin"],
        "points": 4,
    },
    {
        "id": "im_windows_tempered",
        "zone": "immediate",
        "title": "Replace single-pane windows with tempered double-pane",
        "detail": "Radiant heat from a nearby fire shatters single panes long before flame contact.",
        "season": "any",
        "applies_to": ["house", "townhome", "cabin"],
        "points": 3,
    },
    {
        "id": "im_doormat_metal",
        "zone": "immediate",
        "title": "Replace combustible doormats with rubber or coir-on-metal",
        "detail": "A burning welcome mat ignites the door jamb.",
        "season": "any",
        "applies_to": ["house", "townhome", "cabin", "mobile"],
        "points": 2,
    },

    # ─── Intermediate A (1.5–10 m) ──────────────────────────────────────
    {
        "id": "ia_grass_short",
        "zone": "intermediate_a",
        "title": "Mow grass to under 10 cm",
        "detail": "Tall cured grass spreads flame fast and low. Keep mown through dry months.",
        "season": "summer",
        "applies_to": ["house", "townhome", "cabin", "mobile"],
        "points": 4,
    },
    {
        "id": "ia_tree_spacing",
        "zone": "intermediate_a",
        "title": "Space trees so crowns are 3 m+ apart",
        "detail": "Continuous canopy lets fire run tree to tree. Selectively remove or limb.",
        "season": "any",
        "applies_to": ["house", "cabin"],
        "points": 4,
    },
    {
        "id": "ia_no_conifer_close",
        "zone": "intermediate_a",
        "title": "No coniferous (pine, fir, spruce, juniper) within 10 m",
        "detail": "Conifers carry volatile oils and burn hot. Replace with deciduous or non-flammable hardscape.",
        "season": "any",
        "applies_to": ["house", "cabin"],
        "points": 5,
    },
    {
        "id": "ia_ladder_fuels",
        "zone": "intermediate_a",
        "title": "Remove ladder fuels (shrubs under trees)",
        "detail": "Shrubs beneath tree crowns let surface fire climb into the canopy.",
        "season": "any",
        "applies_to": ["house", "cabin"],
        "points": 3,
    },
    {
        "id": "ia_woodpile_distant",
        "zone": "intermediate_a",
        "title": "Move firewood and lumber stacks to ≥ 10 m",
        "detail": "Stacked wood is a massive ember catcher and slow-burning fuel bed.",
        "season": "any",
        "applies_to": ["house", "cabin"],
        "points": 3,
    },

    # ─── Intermediate B (10–30 m) ───────────────────────────────────────
    {
        "id": "ib_limb_trees",
        "zone": "intermediate_b",
        "title": "Limb trees to 2 m above ground",
        "detail": "Removing lower branches breaks the connection between surface fuels and the canopy.",
        "season": "any",
        "applies_to": ["house", "cabin"],
        "points": 4,
    },
    {
        "id": "ib_deadfall",
        "zone": "intermediate_b",
        "title": "Remove dead/down wood and slash piles",
        "detail": "Dry deadfall ignites readily from embers and produces intense local flames.",
        "season": "any",
        "applies_to": ["house", "cabin"],
        "points": 3,
    },
    {
        "id": "ib_thin_canopy",
        "zone": "intermediate_b",
        "title": "Thin canopy so trees are 3–6 m apart at the crowns",
        "detail": "A discontinuous canopy is the single biggest predictor of structure survival in WUI fires.",
        "season": "any",
        "applies_to": ["house", "cabin"],
        "points": 4,
    },

    # ─── Extended (30–100 m) ────────────────────────────────────────────
    {
        "id": "ex_selective_thinning",
        "zone": "extended",
        "title": "Selectively thin dense stands and remove dead trees",
        "detail": "Reduces fireline intensity as a wildfire approaches. Coordinate with neighbours and your local FireSmart rep.",
        "season": "any",
        "applies_to": ["house", "cabin"],
        "points": 3,
    },
    {
        "id": "ex_neighbour_coord",
        "zone": "extended",
        "title": "Coordinate with neighbours on shared FireSmart treatments",
        "detail": "Embers travel >1 km. Your neighbour's untreated lot is your exposure.",
        "season": "any",
        "applies_to": ["house", "townhome", "cabin"],
        "points": 2,
    },

    # ─── Emergency prep cross-cutters ───────────────────────────────────
    {
        "id": "go_bag",
        "zone": "immediate",
        "title": "Pack a 72-hour Grab-and-Go kit",
        "detail": "Per BC Emergency Management: 4 L water/person/day, non-perishable food, prescriptions, ID copies, phone charger, N95 masks for smoke.",
        "season": "any",
        "applies_to": ["house", "townhome", "cabin", "mobile"],
        "points": 5,
    },
    {
        "id": "evac_plan",
        "zone": "immediate",
        "title": "Map two evacuation routes + a meet-up point",
        "detail": "One primary, one backup — both leading away from forested approaches. Practice with everyone in the household.",
        "season": "any",
        "applies_to": ["house", "townhome", "cabin", "mobile"],
        "points": 4,
    },
    {
        "id": "sub_alerts",
        "zone": "immediate",
        "title": "Subscribe to local emergency alerts",
        "detail": "Kamloops + TNRD push alerts via Voyent Alert and Alertable. BC Wildfire Service on X is fastest for incident updates.",
        "season": "any",
        "applies_to": ["house", "townhome", "cabin", "mobile"],
        "points": 3,
    },
]


def _filter_items(dwelling: str, season: str) -> list[dict[str, Any]]:
    d = dwelling.lower()
    s = season.lower()
    return [
        i
        for i in ITEMS
        if d in i["applies_to"] and (i["season"] == "any" or s in (i["season"], "any"))
    ]


def _badges_for(points: int, completed: int, total: int) -> list[dict[str, str]]:
    badges: list[dict[str, str]] = []
    if completed >= 1:
        badges.append({"id": "started", "label": "Got Started", "emoji": "🌱"})
    if completed >= 5:
        badges.append({"id": "ember_aware", "label": "Ember-Aware", "emoji": "🪵"})
    if points >= 25:
        badges.append({"id": "defensible_space", "label": "Defensible Space", "emoji": "🛡️"})
    if total > 0 and completed / total >= 0.5:
        badges.append({"id": "halfway", "label": "Halfway There", "emoji": "🚧"})
    if total > 0 and completed == total:
        badges.append({"id": "firesmart_home", "label": "FireSmart Home", "emoji": "🏆"})
    return badges


@router.get("/checklist", summary="FireSmart HIZ checklist filtered by situation")
async def checklist(
    dwelling: str = "house",
    season: str = "any",
) -> dict[str, Any]:
    items = _filter_items(dwelling, season)
    return Envelope[dict](
        data={
            "zones": ZONES,
            "items": items,
            "max_points": sum(i["points"] for i in items),
        },
        meta=Meta(
            source="firesmart_canada",
            attribution="FireSmart Canada — Home Ignition Zone Assessment",
            phase="5",
        ),
    ).model_dump(mode="json")


@router.post("/score", summary="Compute points + badges from a completed-items list")
async def score(payload: dict[str, Any]) -> dict[str, Any]:
    """Stateless scoring helper. Body: {completed_ids: [...], dwelling, season}.

    Progress lives in the browser, not on the server — this endpoint just
    centralises the badge ladder so rules stay consistent.
    """
    completed_ids = set(payload.get("completed_ids", []) or [])
    dwelling = (payload.get("dwelling") or "house").lower()
    season = (payload.get("season") or "any").lower()

    eligible = _filter_items(dwelling, season)
    total = len(eligible)
    completed = sum(1 for i in eligible if i["id"] in completed_ids)
    points = sum(i["points"] for i in eligible if i["id"] in completed_ids)
    max_points = sum(i["points"] for i in eligible)

    return Envelope[dict](
        data={
            "points": points,
            "max_points": max_points,
            "completed": completed,
            "total": total,
            "badges": _badges_for(points, completed, total),
        },
        meta=Meta(
            source="firesmart_canada",
            attribution="FireSmart Canada",
            phase="5",
        ),
    ).model_dump(mode="json")
