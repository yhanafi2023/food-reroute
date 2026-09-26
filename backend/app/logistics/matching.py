"""find_best_match: pick the driver and drop off plan for one food rescue.

Inputs are plain dicts (the backend converts rows before calling):
  rescue  {id, restaurant_name, meals, lat, lng, pickup_deadline}
  drivers [{id, name, lat, lng, capacity_meals, is_available}]
  needs   [{id, organization_id, organization_name, lat, lng, meals_needed,
            meals_fulfilled, priority, deadline, status}]

Score (lower is better):
  score = pickup_mi + route_mi + 0.1 x eta_min x (1 + urgency)
          - 3 x demand_fit - 2 x priority_bonus - 2 x community_need_fit
  urgency        = clamp(1 - minutes_to_deadline / 180, 0, 1)
  demand_fit     = meals placed on real need / meals available
  priority_bonus = meal weighted average of HIGH 1, MEDIUM 0.5, LOW 0
  community_need_fit = meal weighted average Census-tract poverty score (0 to 1) of the
                       organizations served, see app.community_need -- one optimization
                       factor among feasible plans, never a hard requirement

Distances use the offline road estimate (straight line x 1.3). Times come from the
ETA model (intelligence.eta: gradient boosting trained on real OSRM road-network
times for Miami-Dade, P50 with a calibrated P10 to P90 range, plus an assumed 6
minutes of handling per stop), batched into one prediction call per match. If the
model is unavailable it falls back to the old rule (22 mph + 6 minutes per stop). The real road route
is fetched once, when the driver accepts.
"""
from __future__ import annotations

import heapq
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app import community_need
from app.intelligence.allocation import allocate, demand_fit, remaining_meals
from app.intelligence.eta.model import predict_legs, sum_legs
from app.logistics.geo import haversine_miles, road_miles

TOP_K = 5
URGENCY_HORIZON_MINUTES = 180.0
PRIORITY_BONUS = {"HIGH": 1.0, "MEDIUM": 0.5, "LOW": 0.0}
COMMUNITY_NEED_BONUS_WEIGHT = 2.0  # same scale as PRIORITY_BONUS's max swing, see _evaluate's breakdown


def _community_need_fit(stops: Sequence[Dict[str, Any]]) -> float:
    """Meal-weighted average community-need score (0-1) across a plan's stops."""
    total = sum(s["meals"] for s in stops) or 1
    weighted = sum((community_need.score_for(s["lat"], s["lng"]) or {}).get("community_need_score", 0.0) * s["meals"]
                  for s in stops)
    return weighted / total


def parse_time(value: Any) -> Optional[datetime]:
    """ISO string or datetime to an aware UTC datetime. Naive values are UTC."""
    if value is None or value == "":
        return None
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _now(now: Optional[datetime]) -> datetime:
    return parse_time(now) if now is not None else datetime.now(timezone.utc)


def _order_nearest_neighbor(start, stops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Visit the closest remaining stop next. O(s^2) for s <= 3 stops."""
    ordered, here, left = [], start, list(stops)
    while left:
        nxt = min(left, key=lambda s: haversine_miles(here[0], here[1], s["lat"], s["lng"]))
        ordered.append(nxt)
        left.remove(nxt)
        here = (nxt["lat"], nxt["lng"])
    return ordered


def _plans(meals: int, needs: List[Dict[str, Any]], start) -> List[List[Dict[str, Any]]]:
    """Drop off plans to compare.

    Always the priority based split from intelligence.allocate. Alternatives (a
    nearest-first split, and a single stop run) are added only when they place
    every meal on real need, so an alternative never wins by over-delivering.
    """
    by_id = {n["id"]: n for n in needs}
    nearest_first = [{**n, "priority": "LOW", "deadline": None} for n in needs]
    plans, seen = [], set()
    for pool, max_stops, primary in ((needs, 3, True), (nearest_first, 3, False), (needs, 1, False)):
        allocation = allocate(meals, pool, max_stops=max_stops)
        if not allocation:
            continue
        if not primary and demand_fit(meals, allocation, needs) < 1.0:
            continue
        key = tuple((a["need_id"], a["meals"]) for a in allocation)
        if key in seen:
            continue
        seen.add(key)
        stops = [
            {
                "need_id": a["need_id"],
                "organization_id": by_id[a["need_id"]]["organization_id"],
                "name": by_id[a["need_id"]]["organization_name"],
                "lat": by_id[a["need_id"]]["lat"],
                "lng": by_id[a["need_id"]]["lng"],
                "meals": a["meals"],
                "priority": by_id[a["need_id"]].get("priority", "LOW"),
            }
            for a in allocation
        ]
        plans.append(_order_nearest_neighbor(start, stops))
    return plans


def _stops_summary(stops: Sequence[Dict[str, Any]]) -> str:
    return ", then ".join(f"{s['meals']} meals to {s['name']}" for s in stops)


def _evaluate(rescue, driver, stops, needs, minutes_left: Optional[float], pickup_eta, plan_eta) -> Optional[Dict[str, Any]]:
    """Score one driver x plan. pickup_eta / plan_eta are {p10, p50, p90, source} minutes from the ETA model."""
    r = (rescue["lat"], rescue["lng"])
    pickup_mi = road_miles(driver["lat"], driver["lng"], r[0], r[1])
    arrive_min = pickup_eta["p50"]
    if minutes_left is not None and arrive_min > minutes_left:
        return None  # this driver cannot reach the restaurant before the pickup deadline

    route_mi, here = 0.0, r
    for s in stops:
        route_mi += road_miles(here[0], here[1], s["lat"], s["lng"])
        here = (s["lat"], s["lng"])
    eta = {k: pickup_eta[k] + plan_eta[k] for k in ("p10", "p50", "p90")}
    eta_min = eta["p50"]

    urgency = 0.0 if minutes_left is None else min(max(1 - minutes_left / URGENCY_HORIZON_MINUTES, 0.0), 1.0)
    allocations = [{"need_id": s["need_id"], "meals": s["meals"]} for s in stops]
    fit = demand_fit(rescue["meals"], allocations, needs)
    total = sum(s["meals"] for s in stops) or 1
    bonus = sum(PRIORITY_BONUS.get(str(s["priority"]).upper(), 0.0) * s["meals"] for s in stops) / total
    need_fit = _community_need_fit(stops)

    breakdown = {
        "distance": round(pickup_mi + route_mi, 2),
        "eta": round(0.1 * eta_min, 2),
        "urgency": round(0.1 * eta_min * urgency, 2),
        "demand_fit": round(-3 * fit, 2),
        "priority": round(-2 * bonus, 2),
        "community_need": round(-COMMUNITY_NEED_BONUS_WEIGHT * need_fit, 2),
    }
    return {
        "driver": driver,
        "stops": stops,
        "pickup_miles": pickup_mi,
        "dropoff_miles": route_mi,
        "arrive_minutes": arrive_min,
        "eta_minutes": eta_min,
        "eta_range": (eta["p10"], eta["p90"]),
        "eta_source": "ml" if pickup_eta.get("source") == "ml" else "rule",
        "urgency": urgency,
        "demand_fit": fit,
        "community_need": need_fit,
        "score": round(sum(breakdown.values()), 2),
        "breakdown": breakdown,
    }


def _eta_tables(rescue, drivers, plans):
    """One batched ETA call for every driver -> restaurant leg and every plan's drop off legs."""
    r = (float(rescue["lat"]), float(rescue["lng"]))
    legs = [((d["lat"], d["lng"]), r, 0) for d in drivers]
    spans = []
    for stops in plans:
        start = len(legs)
        here = r
        for s in stops:
            legs.append((here, (s["lat"], s["lng"]), 1))  # 1 handling stop: loading or the previous drop off
            here = (s["lat"], s["lng"])
        spans.append((start, len(legs)))
    preds = predict_legs(legs)
    pickup = preds[: len(drivers)]
    per_plan = [
        {**sum_legs(preds[a:b]), "legs": [round(p["p50"], 1) for p in preds[a:b]]} for a, b in spans
    ]
    return pickup, per_plan


def _reasons(best, options, minutes_left: Optional[float]) -> List[str]:
    d = best["driver"]
    reasons = []
    closest = min(o["pickup_miles"] for o in options)
    if best["pickup_miles"] <= closest + 1e-9:
        reasons.append(f"{d['name']} is {best['pickup_miles']:.1f} mi away, the closest available driver")
    else:
        reasons.append(f"{d['name']} is {best['pickup_miles']:.1f} mi away and gives the best overall route")

    stops = best["stops"]
    if len(stops) > 1:
        reasons.append(
            f"Splits {sum(s['meals'] for s in stops)} meals across {len(stops)} organizations so every meal meets a real need"
        )
    high = [s for s in stops if str(s["priority"]).upper() == "HIGH"]
    if high:
        reasons.append(f"{high[0]['name']} has a HIGH priority need and gets {high[0]['meals']} meals")
    elif len(stops) == 1:
        reasons.append(f"All {stops[0]['meals']} meals go to {stops[0]['name']}")

    if minutes_left is not None and best["urgency"] > 0.5:
        reasons.append(
            f"Pickup deadline is in {minutes_left:.0f} min, so speed was weighted heavily; pickup in about {best['arrive_minutes']:.0f} min"
        )
    else:
        reasons.append(
            f"Total trip {best['pickup_miles'] + best['dropoff_miles']:.1f} mi, about {best['eta_minutes']:.0f} min door to door"
            f" (likely {best['eta_range'][0]:.0f} to {best['eta_range'][1]:.0f} min)"
        )
    if best["community_need"] >= 0.5:
        reasons.append("Serves a Census tract with a higher measured poverty rate (see Community Need)")
    return reasons[:5]


def find_best_match(
    rescue: Dict[str, Any],
    drivers: Iterable[Dict[str, Any]],
    needs: Iterable[Dict[str, Any]],
    exclude_driver_ids: Iterable[Any] = (),
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Best Match for `rescue`, or None if no driver can make the pickup deadline.

    Complexity: the top-k prefilter is O(D log k + N log k) with heapq.nsmallest.
    After that, k drivers x at most 2 plans are scored, so the rest is constant.
    """
    meals = int(rescue["meals"])
    r = (float(rescue["lat"]), float(rescue["lng"]))
    excluded = set(exclude_driver_ids or ())
    deadline = parse_time(rescue.get("pickup_deadline"))
    minutes_left = None if deadline is None else (deadline - _now(now)).total_seconds() / 60.0
    if minutes_left is not None and minutes_left <= 0:
        return None

    eligible = (
        d for d in drivers
        if d.get("is_available", True) and d["id"] not in excluded and int(d.get("capacity_meals") or meals) >= meals
    )
    near_drivers = heapq.nsmallest(TOP_K, eligible, key=lambda d: haversine_miles(d["lat"], d["lng"], r[0], r[1]))
    open_needs = (n for n in needs if n.get("status", "OPEN") == "OPEN" and remaining_meals(n) > 0)
    near_needs = heapq.nsmallest(TOP_K, open_needs, key=lambda n: haversine_miles(n["lat"], n["lng"], r[0], r[1]))
    if not near_drivers or not near_needs:
        return None

    near_needs = [{**n, "distance_miles": haversine_miles(n["lat"], n["lng"], r[0], r[1])} for n in near_needs]
    plans = _plans(meals, near_needs, r)

    pickup_etas, plan_etas = _eta_tables(rescue, near_drivers, plans)
    options = []
    for driver, pickup_eta in zip(near_drivers, pickup_etas):
        for stops, plan_eta in zip(plans, plan_etas):
            option = _evaluate(rescue, driver, stops, near_needs, minutes_left, pickup_eta, plan_eta)
            if option is not None:
                options.append(option)
    if not options:
        return None
    options.sort(key=lambda o: (o["score"], str(o["driver"]["id"])))
    best = options[0]

    return {
        "id": None,
        "rescue_id": rescue.get("id"),
        "driver": {k: best["driver"][k] for k in ("id", "name", "lat", "lng")},
        "stops": [{k: s[k] for k in ("need_id", "organization_id", "name", "lat", "lng", "meals")} for s in best["stops"]],
        "pickup_miles": round(best["pickup_miles"], 2),
        "dropoff_miles": round(best["dropoff_miles"], 2),
        "eta_minutes": round(best["eta_minutes"], 1),
        "eta_range_minutes": [round(best["eta_range"][0], 1), round(best["eta_range"][1], 1)],
        "pickup_eta_minutes": round(best["arrive_minutes"], 1),
        "eta_source": best["eta_source"],
        "score": best["score"],
        "reasons": _reasons(best, options, minutes_left),
        "top_candidates": [
            {
                "driver_name": o["driver"]["name"],
                "stops_summary": _stops_summary(o["stops"]),
                "score": o["score"],
                "breakdown": o["breakdown"],
            }
            for o in options[:3]
        ],
    }
