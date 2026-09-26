"""Distance and offline travel time estimates."""
from __future__ import annotations

import math
from typing import Sequence, Tuple

EARTH_RADIUS_MILES = 3958.8
ROAD_FACTOR = 1.3  # roads are longer than the straight line
AVERAGE_MPH = 22.0  # city driving in Miami, evening traffic
HANDLING_MINUTES_PER_STOP = 6.0  # parking, loading or unloading


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great circle distance in miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def road_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Offline road distance estimate: straight line x 1.3."""
    return haversine_miles(lat1, lng1, lat2, lng2) * ROAD_FACTOR


def drive_minutes(miles: float) -> float:
    return miles / AVERAGE_MPH * 60.0


def path_road_miles(points: Sequence[Tuple[float, float]]) -> float:
    return sum(road_miles(a[0], a[1], b[0], b[1]) for a, b in zip(points, points[1:]))


def offline_eta_minutes(miles: float, stops: int) -> float:
    """Drive time at 22 mph plus 6 minutes of handling per stop."""
    return drive_minutes(miles) + HANDLING_MINUTES_PER_STOP * stops
