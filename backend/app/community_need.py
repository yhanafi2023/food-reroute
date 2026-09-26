"""Community-need (Census poverty) data for the demo's Miami-Dade service area.

Purpose: when several organizations can feasibly receive the same rescue,
FoodFlow can weigh which one serves a community with a higher measured
concentration of economic need -- one input among distance, urgency, demand
and capacity (see app/intelligence/allocation.py::score_need). This never
overrides a hard operational constraint (app/eligibility.py runs first and
removes infeasible organizations entirely) and it never describes individual
people: every figure here is a Census-tract-level area estimate.

Data: backend/data/census_tracts_miami_dade.json, produced once by
scripts/import_census_tracts.py from two real Census Bureau sources (tract
polygons from TIGERweb, poverty statistics from the 2024 ACS 5-Year Estimates,
table S1701). This module never calls the Census API -- see that script's
docstring for why.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import json

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "census_tracts_miami_dade.json"

BUCKET_LABELS = {"low": "Low", "moderate": "Moderate", "high": "High", "very_high": "Very High"}
BUCKET_ORDER = ("low", "moderate", "high", "very_high")
NEED_CEILING_PCT = 40.0  # see community_need_score()


@lru_cache(maxsize=1)
def _dataset() -> Dict[str, Any]:
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def source() -> str:
    return _dataset()["source"]


def bucket_legend() -> List[Dict[str, Any]]:
    """The four visualization buckets, explicitly labeled as ours, not the Bureau's."""
    ranges = {"low": "0-10%", "moderate": "10-20%", "high": "20-30%", "very_high": "30%+"}
    return [{"bucket": b, "label": BUCKET_LABELS[b], "poverty_rate_range": ranges[b]} for b in BUCKET_ORDER]


def community_need_score(poverty_rate: float) -> float:
    """Normalize a tract poverty rate (percent, 0-100) to [0, 1], higher = more measured need.

    Linear up to the NEED_CEILING_PCT ceiling, then clamped, rather than a min-max rescale
    over whatever tracts happen to be loaded -- so one unusually poor (or unusually affluent)
    tract can't single-handedly stretch or compress every other tract's score.
    """
    return max(0.0, min(1.0, poverty_rate / NEED_CEILING_PCT))


def areas() -> List[Dict[str, Any]]:
    """Every loaded tract, for the map's community-need choropleth layer."""
    return [
        {
            "geoid": t["geoid"], "name": t["name"], "poverty_rate": t["poverty_rate"],
            "margin_of_error_pct": t["margin_of_error_pct"], "population": t["population"],
            "population_below_poverty": t["population_below_poverty"], "bucket": t["bucket"],
            "bucket_label": BUCKET_LABELS[t["bucket"]], "community_need_score": t["community_need_score"],
            "geometry": t["geometry"],
        }
        for t in _dataset()["tracts"]
    ]


def _point_in_ring(lat: float, lng: float, ring: List[Tuple[float, float]]) -> bool:
    """Ray casting on [lng, lat] coordinates (same algorithm as app.fleet.geofence.contains)."""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _point_in_geometry(lat: float, lng: float, geometry: Dict[str, Any]) -> bool:
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    return any(_point_in_ring(lat, lng, poly[0]) for poly in polygons)


def tract_for(lat: float, lng: float) -> Optional[Dict[str, Any]]:
    """The tract containing (lat, lng), or None if it falls outside every loaded tract
    (open water, outside the demo's service area, or a gap from simplified geometry --
    handled as a neutral case by callers, never a hard failure)."""
    for t in _dataset()["tracts"]:
        if _point_in_geometry(lat, lng, t["geometry"]):
            return t
    return None


def score_for(lat: float, lng: float) -> Optional[Dict[str, Any]]:
    """Community-need summary for a point, or None when no tract match exists."""
    t = tract_for(lat, lng)
    if t is None:
        return None
    return {
        "geoid": t["geoid"], "name": t["name"], "poverty_rate": t["poverty_rate"],
        "margin_of_error_pct": t["margin_of_error_pct"], "population": t["population"],
        "population_below_poverty": t["population_below_poverty"], "bucket": t["bucket"],
        "bucket_label": BUCKET_LABELS[t["bucket"]], "community_need_score": t["community_need_score"],
        "source": source(),
    }


DISCLAIMER = ("Community Need is an area-level estimate derived from the U.S. Census Bureau's 2024 "
              "American Community Survey 5-Year Estimates. It is used to inform FoodFlow's logistics "
              "optimization and does not describe individual residents.")
