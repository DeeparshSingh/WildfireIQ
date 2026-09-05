"""Tools that act on the user interface rather than returning data.

These are what make the assistant part of the application instead of a
window bolted onto it: asking "show me the fires near Merritt" moves the
globe. The tool itself does nothing — it returns an *effect*, which the
harness streams to the browser, and the browser applies to the Cesium
camera or the layer store.

Effects are deliberately a closed vocabulary. The model cannot invent a UI
action; it can only pick one of these and fill in its arguments, all of
which are validated here.
"""

from __future__ import annotations

from typing import Any

from ._location import LOCATION_PROPERTIES, resolve_location
from .base import ToolArgumentError, ToolResult, tool

#: Map layers, matching `LayerId` in the frontend's layer store.
LAYERS: dict[str, str] = {
    "fires": "Active fire incidents",
    "hotspots": "Satellite thermal hotspots",
    "evac": "Evacuation orders and alerts",
    "smoke": "Smoke plume forecast",
    "fwi": "Fire-weather stations",
    "risk": "AI risk grid",
}

#: Routes, matching the frontend's router.
PAGES: dict[str, str] = {
    "globe": "/",
    "air_quality": "/air-quality",
    "prepare": "/preparedness",
    "climate": "/climate",
    "about": "/about",
}


@tool(
    name="show_on_map",
    description=(
        "Fly the 3D globe to a place and optionally switch on a map layer. Use "
        "this when a location is worth *seeing* — the user asked where "
        "something is, or you just described fires, hexagons or evacuation "
        "zones somewhere. Call it alongside the data tools, not instead of "
        "them, and mention in your answer that you have moved the map."
    ),
    parameters={
        "type": "object",
        "properties": {
            **LOCATION_PROPERTIES,
            "layer": {
                "type": "string",
                "enum": list(LAYERS),
                "description": "Layer to switch on when the camera arrives.",
            },
            "zoom_km": {
                "type": "number",
                "description": "View width in km, 2-500. Default 60.",
            },
            "label": {
                "type": "string",
                "description": "Short caption for the view.",
            },
        },
    },
    ttl_s=0,
    tags=("ui",),
)
def show_on_map(
    place: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    layer: str | None = None,
    zoom_km: float = 60.0,
    label: str | None = None,
) -> ToolResult:
    location = resolve_location(place, lat, lon, required=True)
    if layer is not None and layer not in LAYERS:
        raise ToolArgumentError(f"unknown layer {layer!r}; choose from {', '.join(LAYERS)}")

    zoom_km = max(2.0, min(float(zoom_km), 500.0))
    # A camera height near the span of the area being framed gives roughly
    # the right field of view without needing the viewport's aspect ratio.
    height_m = zoom_km * 1000.0

    effects: list[dict[str, Any]] = [
        {
            "type": "fly_to",
            "lat": location.lat,
            "lon": location.lon,
            "height_m": height_m,
            "label": label or location.label,
        }
    ]
    if layer:
        effects.append({"type": "set_layer", "layer": layer, "visible": True})

    return ToolResult(
        data={
            "moved_to": location.as_dict(),
            "layer_enabled": layer,
            "view_width_km": zoom_km,
        },
        source="WildfireIQ map",
        effects=effects,
        note="The globe has moved. Tell the user what they are now looking at.",
    )


@tool(
    name="set_map_layer",
    description=(
        "Turn a map layer on or off without moving the camera. Use when the "
        "user asks to see or hide a specific overlay."
    ),
    parameters={
        "type": "object",
        "properties": {
            "layer": {
                "type": "string",
                "enum": list(LAYERS),
                "description": "Which layer to change.",
            },
            "visible": {"type": "boolean", "description": "True to show, false to hide."},
        },
        "required": ["layer", "visible"],
    },
    ttl_s=0,
    tags=("ui",),
)
def set_map_layer(layer: str, visible: bool) -> ToolResult:
    if layer not in LAYERS:
        raise ToolArgumentError(f"unknown layer {layer!r}; choose from {', '.join(LAYERS)}")
    return ToolResult(
        data={"layer": layer, "description": LAYERS[layer], "visible": visible},
        source="WildfireIQ map",
        effects=[{"type": "set_layer", "layer": layer, "visible": visible}],
    )


@tool(
    name="open_page",
    description=(
        "Navigate the app to one of its pages. Use when the answer lives in a "
        "dashboard the user should look at: the air-quality forecast charts, "
        "the FireSmart checklist they can tick off, or the climate trend "
        "graphs. Still answer the question in text as well."
    ),
    parameters={
        "type": "object",
        "properties": {
            "page": {
                "type": "string",
                "enum": list(PAGES),
                "description": "Which page to open.",
            },
            "reason": {
                "type": "string",
                "description": "Short phrase on why, shown to the user.",
            },
        },
        "required": ["page"],
    },
    ttl_s=0,
    tags=("ui",),
)
def open_page(page: str, reason: str | None = None) -> ToolResult:
    if page not in PAGES:
        raise ToolArgumentError(f"unknown page {page!r}; choose from {', '.join(PAGES)}")
    return ToolResult(
        data={"page": page, "path": PAGES[page], "reason": reason},
        source="WildfireIQ navigation",
        effects=[{"type": "navigate", "path": PAGES[page], "label": reason or page}],
        # Said here rather than only in the system prompt because this is
        # where the temptation arises. Left to itself the model treats
        # navigating as the whole reply — "The climate page is now open" was
        # its entire answer to a question about fire-danger days.
        note=(
            "The page is open. This is NOT an answer. The user asked a question and "
            "still needs it answered in text, with the actual figures. Answer it now."
        ),
    )
