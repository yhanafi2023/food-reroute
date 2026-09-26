"""Features for one driving leg. Shared by training (real OSRM pairs) and prediction."""
from __future__ import annotations

import math
from typing import Optional, Tuple

BAY_LNG = -80.20  # east of this is Miami Beach; crossing Biscayne Bay means a causeway
HANDLING_MINUTES_PER_STOP = 6.0  # ASSUMPTION: parking + loading/unloading per stop, not learned from data

FEATURES = [
    "crow_miles", "est_road_miles", "provider_miles", "d_lat", "d_lng",
    "start_lat", "start_lng", "end_lat", "end_lng", "crosses_bay",
]


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 3958.8 * math.asin(math.sqrt(a))


def leg_features(start: Tuple[float, float], end: Tuple[float, float], provider_miles: Optional[float] = None) -> dict:
    crow = haversine_miles(start[0], start[1], end[0], end[1])
    return {
        "crow_miles": crow,
        "est_road_miles": crow * 1.3,
        "provider_miles": math.nan if provider_miles is None else float(provider_miles),
        "d_lat": end[0] - start[0],
        "d_lng": end[1] - start[1],
        "start_lat": start[0], "start_lng": start[1], "end_lat": end[0], "end_lng": end[1],
        "crosses_bay": int((start[1] > BAY_LNG) != (end[1] > BAY_LNG)),
    }
