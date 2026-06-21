"""Project-wide constants. Single source of truth for region geometry."""

from typing import Final

# Thompson-Okanagan bounding box.
# Covers Kamloops, Vernon, Kelowna, Salmon Arm, Merritt, Logan Lake, Sun Peaks, Falkland.
BBOX_WEST: Final[float] = -121.5
BBOX_SOUTH: Final[float] = 50.0
BBOX_EAST: Final[float] = -118.5
BBOX_NORTH: Final[float] = 51.5

# (west, south, east, north) — standard order
BBOX: Final[tuple[float, float, float, float]] = (BBOX_WEST, BBOX_SOUTH, BBOX_EAST, BBOX_NORTH)

# Province-wide BC bbox for "show me everything BC Wildfire shows" queries
# (active fires, FIRMS hotspots, FWI stations). Risk modelling stays scoped
# to the Thompson-Okanagan BBOX above.
BC_BBOX_WEST: Final[float] = -139.0
BC_BBOX_SOUTH: Final[float] = 48.3
BC_BBOX_EAST: Final[float] = -114.0
BC_BBOX_NORTH: Final[float] = 60.0
BC_BBOX: Final[tuple[float, float, float, float]] = (
    BC_BBOX_WEST, BC_BBOX_SOUTH, BC_BBOX_EAST, BC_BBOX_NORTH,
)

# Kamloops downtown centroid
KAMLOOPS_LAT: Final[float] = 50.6745
KAMLOOPS_LON: Final[float] = -120.3273

# ECCC station IDs
KAMLOOPS_A_STATION_ID: Final[int] = 1163780  # Kamloops A (current)
KAMLOOPS_OLD_STATION_ID: Final[int] = 1163781  # historical companion

# ─── Risk-model regions ──────────────────────────────────────────────
# Each region is modelled with its own local weather point and its own
# fire history, following the identical methodology. Bounding boxes are
# chosen so they do not overlap; any residual H3-cell overlap is resolved
# by region order (the first region in this list claims a shared cell).
#
# Fields: key, label, anchor city (lat, lon), bbox (west, south, east,
# north), and the weather archive file the region reads.

REGIONS: Final[list[dict]] = [
    {
        "key": "thompson_okanagan",
        "label": "Thompson-Okanagan (Kamloops)",
        "lat": 50.6745,
        "lon": -120.3273,
        "bbox": (-121.5, 50.0, -118.5, 51.5),
        "weather_file": "weather_kamloops_archive_daily.parquet",
    },
    {
        "key": "central_okanagan",
        "label": "Central Okanagan (Kelowna)",
        "lat": 49.8880,
        "lon": -119.4960,
        "bbox": (-120.6, 49.0, -118.5, 50.0),
        "weather_file": "weather_kelowna_archive_daily.parquet",
    },
    {
        "key": "lower_mainland",
        "label": "Lower Mainland (Vancouver)",
        "lat": 49.2497,
        "lon": -123.1193,
        "bbox": (-123.6, 49.0, -121.6, 49.9),
        "weather_file": "weather_vancouver_archive_daily.parquet",
    },
    {
        "key": "prince_george",
        "label": "Prince George (Cariboo)",
        "lat": 53.9171,
        "lon": -122.7497,
        "bbox": (-124.2, 53.0, -121.5, 54.6),
        "weather_file": "weather_prince_george_archive_daily.parquet",
    },
]

# Cesium camera default
CAMERA_DEFAULT_HEIGHT_M: Final[int] = 180_000
