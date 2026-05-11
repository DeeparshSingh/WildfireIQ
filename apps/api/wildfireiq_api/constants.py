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

# Kamloops downtown centroid
KAMLOOPS_LAT: Final[float] = 50.6745
KAMLOOPS_LON: Final[float] = -120.3273

# ECCC station IDs
KAMLOOPS_A_STATION_ID: Final[int] = 1163780  # Kamloops A (current)
KAMLOOPS_OLD_STATION_ID: Final[int] = 1163781  # historical companion

# Cesium camera default
CAMERA_DEFAULT_HEIGHT_M: Final[int] = 180_000
