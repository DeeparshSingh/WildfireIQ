"""Offline place-name resolution for British Columbia.

Every location-aware tool accepts a free-text `place` as an alternative to
raw coordinates, because that is how people ask ("is Logan Lake under an
evacuation alert?"). Resolving those names through a hosted geocoder would
add a second API key, a second failure mode, and a per-question network
round trip to a service that knows nothing about wildfire.

Instead the gazetteer is a fixed table: the four modelled region anchors,
the fourteen Kamloops neighbourhoods the FireSmart hub already ships, and
the BC communities that actually appear in fire and evacuation coverage.
It is small, instant, and its failures are legible — an unknown name comes
back as "unknown" with near-miss suggestions rather than a confident
coordinate somewhere in Ontario.
"""

from __future__ import annotations

import json
import math
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from ..constants import REGIONS
from ..paths import GEO_ROOT

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True, slots=True)
class Place:
    name: str
    lat: float
    lon: float
    kind: str  # "region" | "neighbourhood" | "community"
    region_key: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "lat": round(self.lat, 5),
            "lon": round(self.lon, 5),
            "kind": self.kind,
            "region": self.region_key,
        }


# BC communities inside or adjacent to the modelled regions, plus the
# larger centres people use as landmarks. Coordinates are municipal
# centroids to 4 decimals (~10 m), which is far finer than anything the
# H3 r=5 grid or the evacuation polygons need.
_COMMUNITIES: tuple[tuple[str, float, float], ...] = (
    ("Kamloops", 50.6745, -120.3273),
    ("Kelowna", 49.8880, -119.4960),
    ("West Kelowna", 49.8625, -119.6433),
    ("Vernon", 50.2670, -119.2720),
    ("Penticton", 49.4991, -119.5937),
    ("Summerland", 49.6006, -119.6706),
    ("Peachland", 49.7714, -119.7375),
    ("Osoyoos", 49.0325, -119.4682),
    ("Oliver", 49.1830, -119.5500),
    ("Merritt", 50.1113, -120.7862),
    ("Logan Lake", 50.4936, -120.8083),
    ("Ashcroft", 50.7222, -121.2811),
    ("Cache Creek", 50.8117, -121.3242),
    ("Lytton", 50.2317, -121.5814),
    ("Lillooet", 50.6861, -121.9364),
    ("Clinton", 51.0919, -121.5878),
    ("Barriere", 51.1858, -120.1233),
    ("Clearwater", 51.6508, -120.0339),
    ("Blue River", 52.1189, -119.2903),
    ("Chase", 50.8194, -119.6858),
    ("Sorrento", 50.8828, -119.4703),
    ("Salmon Arm", 50.7001, -119.2838),
    ("Sicamous", 50.8358, -118.9808),
    ("Enderby", 50.5508, -119.1394),
    ("Armstrong", 50.4472, -119.1936),
    ("Lake Country", 50.0500, -119.4100),
    ("Revelstoke", 50.9981, -118.1957),
    ("Golden", 51.2970, -116.9631),
    ("Sun Peaks", 50.8836, -119.8869),
    ("Princeton", 49.4586, -120.5106),
    ("Keremeos", 49.2050, -119.8283),
    ("Hope", 49.3828, -121.4414),
    ("Chilliwack", 49.1579, -121.9515),
    ("Abbotsford", 49.0504, -122.3045),
    ("Mission", 49.1337, -122.3126),
    ("Maple Ridge", 49.2193, -122.5984),
    ("Langley", 49.1044, -122.6603),
    ("Surrey", 49.1913, -122.8490),
    ("Delta", 49.0847, -123.0587),
    ("Richmond", 49.1666, -123.1336),
    ("Burnaby", 49.2488, -122.9805),
    ("Coquitlam", 49.2838, -122.7932),
    ("New Westminster", 49.2057, -122.9110),
    ("North Vancouver", 49.3200, -123.0724),
    ("West Vancouver", 49.3286, -123.1603),
    ("Vancouver", 49.2497, -123.1193),
    ("Squamish", 49.7016, -123.1558),
    ("Whistler", 50.1163, -122.9574),
    ("Pemberton", 50.3192, -122.8064),
    ("Victoria", 48.4284, -123.3656),
    ("Nanaimo", 49.1659, -123.9401),
    ("Port Alberni", 49.2339, -124.8055),
    ("Courtenay", 49.6877, -124.9936),
    ("Campbell River", 50.0244, -125.2475),
    ("Powell River", 49.8353, -124.5247),
    ("Sechelt", 49.4742, -123.7600),
    ("Prince George", 53.9171, -122.7497),
    ("Quesnel", 52.9784, -122.4927),
    ("Williams Lake", 52.1417, -122.1417),
    ("100 Mile House", 51.6428, -121.2969),
    ("Vanderhoof", 54.0136, -124.0122),
    ("Fort St. James", 54.4433, -124.2517),
    ("Burns Lake", 54.2286, -125.7608),
    ("Houston", 54.3986, -126.6672),
    ("Smithers", 54.7822, -127.1686),
    ("Terrace", 54.5182, -128.6032),
    ("Kitimat", 54.0524, -128.6534),
    ("Prince Rupert", 54.3150, -130.3208),
    ("Mackenzie", 55.3372, -123.0936),
    ("Dawson Creek", 55.7596, -120.2377),
    ("Fort St. John", 56.2465, -120.8476),
    ("Fort Nelson", 58.8050, -122.7002),
    ("Nelson", 49.4928, -117.2948),
    ("Castlegar", 49.3239, -117.6594),
    ("Trail", 49.0966, -117.7117),
    ("Grand Forks", 49.0303, -118.4406),
    ("Cranbrook", 49.5097, -115.7686),
    ("Kimberley", 49.6697, -115.9775),
    ("Invermere", 50.5061, -116.0322),
    ("Fernie", 49.5042, -115.0631),
    ("Sparwood", 49.7328, -114.8853),
    ("Creston", 49.0955, -116.5135),
    ("Kaslo", 49.9139, -116.9114),
    ("Nakusp", 50.2400, -117.8000),
)


@lru_cache(maxsize=1)
def all_places() -> tuple[Place, ...]:
    """The full gazetteer, built once.

    Order matters only for tie-breaking: regions first so "Thompson-Okanagan"
    resolves to the modelled region rather than to Kamloops the city.
    """
    places: list[Place] = []

    for region in REGIONS:
        places.append(
            Place(
                name=str(region["label"]),
                lat=float(region["lat"]),
                lon=float(region["lon"]),
                kind="region",
                region_key=str(region["key"]),
            )
        )

    for name, lat, lon in _COMMUNITIES:
        places.append(
            Place(name=name, lat=lat, lon=lon, kind="community", region_key=region_for(lat, lon))
        )

    # Kamloops neighbourhoods come from the same GeoJSON the FireSmart
    # onboarding wizard uses, so the two surfaces can never disagree about
    # which neighbourhoods exist.
    path = GEO_ROOT / "kamloops_neighbourhoods.geojson"
    if path.exists():
        try:
            features = json.loads(path.read_text()).get("features", [])
        except (OSError, json.JSONDecodeError):
            features = []
        for feature in features:
            props = feature.get("properties") or {}
            name = props.get("name")
            lat, lon = props.get("centroid_lat"), props.get("centroid_lon")
            if not name or lat is None or lon is None:
                continue
            places.append(
                Place(
                    name=f"{name}, Kamloops",
                    lat=float(lat),
                    lon=float(lon),
                    kind="neighbourhood",
                    region_key="thompson_okanagan",
                )
            )

    return tuple(places)


def _normalise(text: str) -> str:
    """Fold case, accents, and punctuation so 'Ft. St. John' matches."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    kept = [c.lower() if (c.isalnum() or c.isspace()) else " " for c in stripped]
    return " ".join("".join(kept).split())


@lru_cache(maxsize=1)
def _index() -> dict[str, Place]:
    """Normalised name → place, including a bare-name alias for suburbs."""
    idx: dict[str, Place] = {}
    for place in all_places():
        idx.setdefault(_normalise(place.name), place)
        # "Aberdeen" as well as "Aberdeen, Kamloops"; "Thompson-Okanagan"
        # as well as "Thompson-Okanagan (Kamloops)".
        head = place.name.split(",")[0].split("(")[0].strip()
        if head and head != place.name:
            idx.setdefault(_normalise(head), place)
    return idx


@dataclass(frozen=True, slots=True)
class Resolution:
    place: Place | None
    confidence: str  # "exact" | "prefix" | "fuzzy" | "none"
    alternatives: tuple[Place, ...] = ()


def resolve(query: str, *, limit: int = 4) -> Resolution:
    """Resolve a free-text place name against the gazetteer.

    Three passes, widening: exact normalised match, then prefix/substring,
    then word overlap. Anything that gets past none of them returns
    `confidence="none"` with the closest names as suggestions, which the
    model can offer the user instead of inventing a coordinate.
    """
    key = _normalise(query or "")
    if not key:
        return Resolution(None, "none")

    index = _index()
    if hit := index.get(key):
        return Resolution(hit, "exact")

    # Drop a trailing province qualifier: "Kelowna BC", "Merritt, British Columbia".
    for suffix in (" bc", " b c", " british columbia", " canada"):
        if key.endswith(suffix):
            trimmed = key[: -len(suffix)].strip()
            if hit := index.get(trimmed):
                return Resolution(hit, "exact")
            key = trimmed or key
            break

    prefix = [p for name, p in index.items() if name.startswith(key) or key.startswith(name)]
    if prefix:
        best = min(prefix, key=lambda p: len(p.name))
        return Resolution(best, "prefix", tuple(_dedupe(prefix)[:limit]))

    words = set(key.split())
    scored: list[tuple[int, Place]] = []
    for name, place in index.items():
        overlap = len(words & set(name.split()))
        if overlap:
            scored.append((overlap, place))
    if scored:
        scored.sort(key=lambda t: (-t[0], len(t[1].name)))
        return Resolution(scored[0][1], "fuzzy", tuple(_dedupe([p for _, p in scored])[:limit]))

    return Resolution(None, "none", tuple(all_places()[:limit]))


def _dedupe(places: list[Place]) -> list[Place]:
    seen: set[str] = set()
    out: list[Place] = []
    for place in places:
        if place.name not in seen:
            seen.add(place.name)
            out.append(place)
    return out


def region_for(lat: float, lon: float) -> str | None:
    """Which modelled region contains this point, if any.

    Region order is the tie-break, matching the feature builder's
    first-claim-wins rule so a point never reports one region here and a
    different one on the map.
    """
    for region in REGIONS:
        west, south, east, north = region["bbox"]
        if west <= lon <= east and south <= lat <= north:
            return str(region["key"])
    return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def nearest_place(
    lat: float, lon: float, *, kinds: tuple[str, ...] = ("community",)
) -> Place | None:
    """Closest gazetteer entry to a coordinate — used to label raw points."""
    candidates = [p for p in all_places() if p.kind in kinds]
    if not candidates:
        return None
    return min(candidates, key=lambda p: haversine_km(lat, lon, p.lat, p.lon))
