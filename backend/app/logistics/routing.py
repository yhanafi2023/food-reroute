"""Road routes for a list of points: Mapbox Directions, OSRM, or an offline estimate.

Provider choice (ROUTING_PROVIDER env var):
  mapbox   Mapbox Directions API (needs MAPBOX_ACCESS_TOKEN)
  osrm     OSRM (OSRM_URL, default https://router.project-osrm.org)
  offline  straight line x 1.3 at 22 mph, no network at all
When ROUTING_PROVIDER is not set: mapbox if a token is present, else offline in
DEMO_MODE, else osrm. Any network failure or timeout (3 seconds) falls back to
the offline estimate, so the demo keeps working with wifi turned off.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Sequence, Tuple

import httpx

from app.logistics.geo import HANDLING_MINUTES_PER_STOP, offline_eta_minutes, path_road_miles

METERS_PER_MILE = 1609.344
TIMEOUT_SECONDS = 3.0

_cache: Dict[Tuple[str, Tuple[Tuple[float, float], ...]], Dict[str, Any]] = {}


def _point(p: Any) -> Tuple[float, float]:
    if isinstance(p, dict):
        return float(p["lat"]), float(p["lng"])
    if isinstance(p, (list, tuple)):
        return float(p[0]), float(p[1])
    return float(p.lat), float(p.lng)


def provider() -> str:
    chosen = os.getenv("ROUTING_PROVIDER", "").strip().lower()
    if chosen in ("mapbox", "osrm", "offline"):
        return chosen
    if os.getenv("MAPBOX_ACCESS_TOKEN"):
        return "mapbox"
    if os.getenv("DEMO_MODE", "false").lower() == "true":
        return "offline"
    return "osrm"


def offline_route(points: Sequence[Tuple[float, float]]) -> Dict[str, Any]:
    miles = path_road_miles(points)
    return {
        "geometry": [[lat, lng] for lat, lng in points],
        "distance_miles": round(miles, 2),
        "eta_minutes": round(offline_eta_minutes(miles, len(points) - 1), 1),
        "source": "offline",
    }


def _from_directions(route: Dict[str, Any], stops: int, source: str) -> Dict[str, Any]:
    coords = route["geometry"]["coordinates"]  # GeoJSON is [lng, lat]
    return {
        "geometry": [[round(lat, 6), round(lng, 6)] for lng, lat in coords],
        "distance_miles": round(route["distance"] / METERS_PER_MILE, 2),
        "eta_minutes": round(route["duration"] / 60.0 + HANDLING_MINUTES_PER_STOP * stops, 1),
        "source": source,
    }


def _mapbox(points: Sequence[Tuple[float, float]]) -> Dict[str, Any]:
    token = os.environ["MAPBOX_ACCESS_TOKEN"]
    coords = ";".join(f"{lng},{lat}" for lat, lng in points)
    resp = httpx.get(
        f"https://api.mapbox.com/directions/v5/mapbox/driving/{coords}",
        params={"geometries": "geojson", "overview": "full", "access_token": token},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return _from_directions(resp.json()["routes"][0], len(points) - 1, "mapbox")


def _osrm(points: Sequence[Tuple[float, float]]) -> Dict[str, Any]:
    base = os.getenv("OSRM_URL", "https://router.project-osrm.org").rstrip("/")
    coords = ";".join(f"{lng},{lat}" for lat, lng in points)
    resp = httpx.get(
        f"{base}/route/v1/driving/{coords}",
        params={"geometries": "geojson", "overview": "full"},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "Ok":
        raise ValueError(f"OSRM error {data.get('code')}")
    return _from_directions(data["routes"][0], len(points) - 1, "osrm")


def get_route(points: Sequence[Any]) -> Dict[str, Any]:
    """Route through `points` in order. Returns the Route contract object."""
    pts = tuple(_point(p) for p in points)
    if len(pts) < 2:
        return {"geometry": [list(p) for p in pts], "distance_miles": 0.0, "eta_minutes": 0.0, "source": "offline"}
    chosen = provider()
    key = (chosen, tuple((round(a, 5), round(b, 5)) for a, b in pts))
    if key in _cache:
        return _cache[key]
    route: Dict[str, Any]
    try:
        if chosen == "mapbox":
            route = _mapbox(pts)
        elif chosen == "osrm":
            route = _osrm(pts)
        else:
            route = offline_route(pts)
    except Exception:
        # Network down, timeout, bad token, or no road route: never break the demo.
        return offline_route(pts)
    _cache[key] = route
    return route


def clear_cache() -> None:
    _cache.clear()
