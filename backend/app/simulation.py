"""Simulate Tonight: a 60 second accelerated Miami evening (6 PM to 10 PM), SIMULATED DATA.

Runs the real matching (find_best_match, which uses intelligence.allocate) and
routing code over the demo network with a fixed random seed, so it plays out the
same way every time. It never touches the database. Returns timed events the
admin map plays back: rescue_posted, matched (with the route to animate along),
delivered (with running impact totals), and unmatched.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from app.logistics import find_best_match, get_route
from app.seed import DRIVERS, ORGANIZATIONS, RESTAURANTS

SEED = 2026
SIM_MINUTES = 240  # 6 PM to 10 PM
DURATION_MS = 60_000
MS_PER_MIN = DURATION_MS / SIM_MINUTES
MATCH_DELAY_MIN = 2
LBS_PER_MEAL = 1.2
SIM_START = datetime(2026, 9, 26, 22, 0, tzinfo=timezone.utc)  # 6 PM in Miami (UTC-4)
SIM_NEEDS = {"Community Food Bank": 30, "Hope Shelter": 20, "Westchester Church Pantry": 150, "FIU Student Pantry": 35}
FOOD = ["Rice and beans", "Sandwiches", "Pastries", "Pizza", "Mixed trays", "Salads", "Roast chicken"]


def _clock(minute: float) -> str:
    total = 18 * 60 + int(minute)
    h, m = divmod(total, 60)
    return f"{(h - 1) % 12 + 1}:{m:02d} {'PM' if h >= 12 else 'AM'}"


def _ms(minute: float) -> int:
    return int(round(minute * MS_PER_MIN))


def build_simulation(seed: int = SEED) -> Dict[str, Any]:
    rng = random.Random(seed)
    restaurants = [{"name": r[0], "lat": r[5], "lng": r[6]} for r in RESTAURANTS]
    drivers = [
        {"id": i + 1, "name": d[0], "lat": d[2], "lng": d[3], "capacity_meals": d[4], "is_available": True, "free_at": 0.0}
        for i, d in enumerate(DRIVERS)
    ]
    needs = [
        {"id": i + 1, "organization_id": i + 1, "organization_name": o[0], "lat": o[3], "lng": o[4],
         "meals_needed": SIM_NEEDS[o[0]], "meals_fulfilled": 0, "priority": o[7],
         "deadline": SIM_START + timedelta(hours=6), "status": "OPEN"}
        for i, o in enumerate(ORGANIZATIONS)
    ]

    # The first rescue is the demo story: ABC posts 50 meals that split 30 / 20.
    rescues = [{"minute": 5.0, "restaurant": restaurants[0], "meals": 50, "deadline_min": 240.0, "food": "Rice and beans"}]
    for minute in sorted(rng.uniform(12, 185) for _ in range(9)):
        rescues.append({
            "minute": round(minute, 1),
            "restaurant": rng.choice(restaurants),
            "meals": rng.randint(12, 28),
            "deadline_min": minute + rng.randint(40, 120),
            "food": rng.choice(FOOD),
        })

    events: List[Dict[str, Any]] = []
    for i, r in enumerate(rescues, start=1):
        t = r["minute"]
        rest = r["restaurant"]
        rescue = {"id": i, "restaurant_name": rest["name"], "meals": r["meals"], "lat": rest["lat"], "lng": rest["lng"],
                  "pickup_deadline": SIM_START + timedelta(minutes=r["deadline_min"])}
        events.append({"t_ms": _ms(t), "clock": _clock(t), "type": "rescue_posted",
                       "rescue": {**rescue, "pickup_deadline": rescue["pickup_deadline"].isoformat(), "food_type": r["food"]}})

        t_match = t + MATCH_DELAY_MIN
        free = [d for d in drivers if d["free_at"] <= t_match]
        match = find_best_match(rescue, free, needs, now=SIM_START + timedelta(minutes=t_match))
        if match is None:
            events.append({"t_ms": _ms(t_match), "clock": _clock(t_match), "type": "unmatched", "rescue_id": i,
                           "reason": "No driver free or no open need nearby at that moment"})
            continue

        driver = next(d for d in drivers if d["id"] == match["driver"]["id"])
        route = get_route([(driver["lat"], driver["lng"]), (rest["lat"], rest["lng"])]
                          + [(s["lat"], s["lng"]) for s in match["stops"]])
        trip = match["eta_minutes"]  # ML ETA (real OSRM road-network times + assumed handling), same as live matching
        t_done = t_match + trip
        events.append({
            "t_ms": _ms(t_match), "clock": _clock(t_match), "type": "matched", "rescue_id": i,
            "driver": match["driver"], "stops": match["stops"], "route": route, "reasons": match["reasons"],
            "eta_range_minutes": match["eta_range_minutes"],
            "eta_minutes": trip, "duration_ms": _ms(trip),
        })
        events.append({"t_ms": _ms(t_done), "clock": _clock(t_done), "type": "delivered", "rescue_id": i,
                       "driver_id": driver["id"], "restaurant_name": rest["name"], "meals": r["meals"],
                       "stops": [{"name": s["name"], "meals": s["meals"]} for s in match["stops"]],
                       "minutes": round(trip, 1)})

        driver["free_at"] = t_done
        driver["lat"], driver["lng"] = match["stops"][-1]["lat"], match["stops"][-1]["lng"]
        for s in match["stops"]:
            need = next(n for n in needs if n["id"] == s["need_id"])
            need["meals_fulfilled"] += s["meals"]

    events.sort(key=lambda e: (e["t_ms"], e["type"] != "rescue_posted"))
    totals = {"meals_rescued": 0, "lbs_diverted": 0.0, "deliveries_completed": 0}
    restaurants_served, orgs_served = set(), set()
    for e in events:
        if e["type"] == "delivered":
            totals["meals_rescued"] += e["meals"]
            totals["lbs_diverted"] = round(totals["lbs_diverted"] + e["meals"] * LBS_PER_MEAL, 1)
            totals["deliveries_completed"] += 1
            restaurants_served.add(e["restaurant_name"])
            orgs_served.update(s["name"] for s in e["stops"])
            e["impact"] = dict(totals)

    return {
        "label": "Simulated data",
        "seed": seed,
        "duration_ms": DURATION_MS,
        "start_clock": _clock(0),
        "end_clock": _clock(SIM_MINUTES),
        "events": events,
        "summary": {**totals, "restaurants": len(restaurants_served), "organizations": len(orgs_served),
                    "rescues_posted": len(rescues)},
    }
