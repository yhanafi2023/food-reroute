"""Address search for sign-up: turns a typed street address into the pickup / drop-off point that
matching and routing use. Mapbox Geocoding when MAPBOX_ACCESS_TOKEN is set, else OpenStreetMap's
Nominatim (free, 1 request/second, fine for sign-ups). Results lean toward Miami."""
import os
import threading
import time
from typing import Dict, List, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["geo"])

MIAMI = (25.7574, -80.3733)
_cache: Dict[str, Tuple[float, List[dict]]] = {}
_lock = threading.Lock()
_last_nominatim = [0.0]


def _mapbox(q: str, token: str) -> List[dict]:
    r = httpx.get("https://api.mapbox.com/search/geocode/v6/forward", timeout=6,
                  params={"q": q, "access_token": token, "limit": 5, "country": "us",
                          "proximity": f"{MIAMI[1]},{MIAMI[0]}", "types": "address,street,poi"})
    r.raise_for_status()
    return [{"label": f["properties"].get("full_address") or f["properties"].get("name", q),
             "lat": f["geometry"]["coordinates"][1], "lng": f["geometry"]["coordinates"][0]}
            for f in r.json().get("features", [])]


def _nominatim(q: str) -> List[dict]:
    with _lock:  # the public server allows one request per second
        wait = 1.0 - (time.monotonic() - _last_nominatim[0])
        if wait > 0:
            time.sleep(wait)
        _last_nominatim[0] = time.monotonic()
    r = httpx.get("https://nominatim.openstreetmap.org/search", timeout=6,
                  headers={"User-Agent": "FoodFlow food-rescue app (sign-up address search)"},
                  params={"q": q, "format": "jsonv2", "limit": 5, "countrycodes": "us", "addressdetails": 0,
                          "viewbox": "-80.9,26.2,-80.0,25.3", "bounded": 0})
    r.raise_for_status()
    return [{"label": p["display_name"], "lat": float(p["lat"]), "lng": float(p["lon"])} for p in r.json()]


@router.get("/geo/search")
def search(q: str = Query(min_length=5, max_length=200)):
    key = " ".join(q.lower().split())
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 24 * 3600:
        return {"results": hit[1]}
    token = os.getenv("MAPBOX_ACCESS_TOKEN")
    try:
        results = _mapbox(q, token) if token else _nominatim(q)
    except httpx.HTTPError:
        raise HTTPException(503, "Address search is unavailable right now. Try again in a moment.")
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (time.time(), results)
    return {"results": results}
