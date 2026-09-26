"""Service-area geofence for simulated autonomous vehicles.

Loaded from data/av_zone_illustrative.geojson, labeled "illustrative demo zone":
NOT an official Waymo service area.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

ZONE_FILE = Path(__file__).resolve().parents[2] / "data" / "av_zone_illustrative.geojson"


@lru_cache(maxsize=1)
def zone() -> Dict:
    doc = json.loads(ZONE_FILE.read_text())
    feature = doc["features"][0]
    return {"name": feature["properties"]["name"], "label": feature["properties"]["label"],
            "note": feature["properties"]["note"], "ring": feature["geometry"]["coordinates"][0], "geojson": doc}


def contains(lat: float, lng: float) -> bool:
    """Ray casting point-in-polygon on [lng, lat] coordinates."""
    ring: List[Tuple[float, float]] = zone()["ring"]
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside
