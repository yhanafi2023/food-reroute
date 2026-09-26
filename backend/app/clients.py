"""Calls to the routing (Role 3) and allocation (Role 4) services, with fallbacks.

ROUTING_SERVICE_URL / ALLOCATION_SERVICE_URL: call a teammate's HTTP service.
Unset: use the in-process modules (app.intelligence.eta, app.intelligence.allocation).
If the service fails or times out, fall back per the spec and flag estimated=True:
  travel: haversine distance x 1.3 at 30 km/h (plus the stated handling assumption)
  allocation: nearest eligible organization takes the meals (up to its capacity)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Sequence, Tuple

import httpx

from app.assumptions import FALLBACK_ROAD_FACTOR, FALLBACK_SPEED_KMH
from app.config import ALLOCATION_SERVICE_URL, ROUTING_SERVICE_URL, SERVICE_TIMEOUT_SECONDS
from app.intelligence.allocation import allocate as allocate_in_process
from app.intelligence.eta.features import HANDLING_MINUTES_PER_STOP, haversine_miles
from app.intelligence.eta.model import predict_legs

log = logging.getLogger("foodflow.clients")
Point = Tuple[float, float]
Leg = Tuple[Point, Point, int]


def _fallback_minutes(leg: Leg) -> float:
    km = haversine_miles(leg[0][0], leg[0][1], leg[1][0], leg[1][1]) * 1.609344 * FALLBACK_ROAD_FACTOR
    return km / FALLBACK_SPEED_KMH * 60 + HANDLING_MINUTES_PER_STOP * leg[2]


def travel(legs: Sequence[Leg]) -> Tuple[List[Dict[str, float]], bool, str]:
    """[{p10, p50, p90}] minutes per leg, estimated flag, source."""
    if not legs:
        return [], False, "none"
    try:
        if ROUTING_SERVICE_URL:
            r = httpx.post(f"{ROUTING_SERVICE_URL}/eta", timeout=SERVICE_TIMEOUT_SECONDS, json={
                "legs": [{"from": list(a), "to": list(b), "handling_stops": h} for a, b, h in legs]})
            r.raise_for_status()
            mins = r.json()["minutes"]
            if len(mins) != len(legs):
                raise ValueError("routing service returned the wrong number of legs")
            return [{k: float(m[k]) for k in ("p10", "p50", "p90")} for m in mins], False, "routing_service"
        preds = predict_legs(list(legs))
        return [{k: p[k] for k in ("p10", "p50", "p90")} for p in preds], preds[0]["source"] != "ml", "eta_model"
    except Exception as e:
        log.warning("routing unavailable, using fallback estimate: %s", e)
        return [dict.fromkeys(("p10", "p50", "p90"), _fallback_minutes(leg)) for leg in legs], True, "fallback"


def allocate(meals: int, needs: List[Dict[str, Any]]) -> Tuple[List[Dict[str, int]], bool, str]:
    """Split meals across eligible orgs. needs carry every constraint the service must respect."""
    if not needs:
        return [], False, "none"
    by_id = {n["id"]: n for n in needs}
    try:
        if ALLOCATION_SERVICE_URL:
            r = httpx.post(f"{ALLOCATION_SERVICE_URL}/allocate", timeout=SERVICE_TIMEOUT_SECONDS,
                           json={"meals": meals, "needs": needs})
            r.raise_for_status()
            allocations = r.json()["allocations"]
            for a in allocations:  # never trust a remote answer that breaks our eligibility rules
                n = by_id.get(a["need_id"])
                if n is None or a["meals"] <= 0 or a["meals"] > n["meals_needed"]:
                    raise ValueError(f"allocation service returned an invalid allocation: {a}")
            return allocations, False, "allocation_service"
        allocations = allocate_in_process(meals, needs)
        # the in-process allocator gives leftovers to the top need; cap at each org's stated capacity
        return [{"need_id": a["need_id"], "meals": min(a["meals"], by_id[a["need_id"]]["meals_needed"])}
                for a in allocations if min(a["meals"], by_id[a["need_id"]]["meals_needed"]) > 0], False, "allocation_model"
    except Exception as e:
        log.warning("allocation unavailable, using nearest eligible org: %s", e)
        nearest = min(needs, key=lambda n: n.get("distance_miles", 0))
        return [{"need_id": nearest["id"], "meals": min(meals, nearest["meals_needed"])}], True, "fallback"
