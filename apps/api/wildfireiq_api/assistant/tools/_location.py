"""Shared location handling for tools that accept a place or a coordinate.

Users ask about places; the data is indexed by coordinates. Every
location-aware tool takes the same three optional arguments so the model
never has to remember which tool wants which, and they are resolved here
once.
"""

from __future__ import annotations

from typing import Any

from .. import gazetteer
from .base import ToolArgumentError

#: Reusable JSON Schema fragment. Spread into a tool's `properties`.
#:
#: Deliberately terse: this block appears in ten of the twenty-five tool
#: schemas, and every schema is re-sent to the model on every turn of every
#: run, so a sentence saved here is saved ten times per turn.
LOCATION_PROPERTIES: dict[str, Any] = {
    "place": {
        "type": "string",
        "description": (
            "BC place name — city, town, modelled region, or Kamloops "
            "neighbourhood. Prefer this when the user named a place."
        ),
    },
    "lat": {"type": "number", "description": "Latitude, decimal degrees."},
    "lon": {"type": "number", "description": "Longitude, decimal degrees."},
}

LOCATION_HINT = (
    "Give either `place` or both `lat` and `lon`. "
    "Omit all three to use the user's current map location if they shared one, "
    "otherwise Kamloops."
)


class ResolvedLocation:
    """A coordinate plus the label to describe it by."""

    __slots__ = ("label", "lat", "lon", "region_key", "source")

    def __init__(self, lat: float, lon: float, label: str, region_key: str | None, source: str):
        self.lat = lat
        self.lon = lon
        self.label = label
        self.region_key = region_key
        self.source = source  # "place" | "coordinates" | "default"

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "lat": round(self.lat, 5),
            "lon": round(self.lon, 5),
            "region": self.region_key,
            "resolved_from": self.source,
        }


#: Fallback when the user named nothing and shared nothing. Kamloops is the
#: platform's home city, so it is the right default rather than an arbitrary one.
_DEFAULT = (50.6745, -120.3273, "Kamloops")


def resolve_location(
    place: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    *,
    required: bool = False,
) -> ResolvedLocation:
    """Turn a tool's location arguments into one coordinate.

    Explicit coordinates win over a name, because a coordinate is what the
    frontend sends when the user clicked the map — it is more specific than
    anything they could have typed.
    """
    if lat is not None and lon is not None:
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            raise ToolArgumentError(f"coordinates out of range: lat={lat}, lon={lon}")
        near = gazetteer.nearest_place(lat, lon)
        label = f"{lat:.4f}, {lon:.4f}"
        if near is not None:
            distance = gazetteer.haversine_km(lat, lon, near.lat, near.lon)
            label = near.name if distance < 3 else f"{distance:.0f} km from {near.name}"
        return ResolvedLocation(lat, lon, label, gazetteer.region_for(lat, lon), "coordinates")

    if place:
        resolution = gazetteer.resolve(place)
        if resolution.place is None:
            suggestions = ", ".join(p.name for p in resolution.alternatives[:4])
            raise ToolArgumentError(
                f"'{place}' is not in the British Columbia gazetteer. "
                f"Did you mean one of: {suggestions}? "
                "Otherwise ask the user for coordinates."
            )
        found = resolution.place
        return ResolvedLocation(
            found.lat,
            found.lon,
            found.name,
            found.region_key or gazetteer.region_for(found.lat, found.lon),
            "place",
        )

    if required:
        raise ToolArgumentError(f"a location is required. {LOCATION_HINT}")

    lat0, lon0, label = _DEFAULT
    return ResolvedLocation(lat0, lon0, label, gazetteer.region_for(lat0, lon0), "default")
