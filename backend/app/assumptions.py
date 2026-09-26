"""Every configurable number FoodFlow relies on, with where it comes from.

"assumption" means FoodFlow chose the value for planning; replace it with measured
data when available. "cited" means the value comes from the named source.
Served at GET /config/assumptions so the UI and docs never hard-code them.
"""
from __future__ import annotations

import os
from typing import Any, Dict


def _f(name: str, default: float) -> float:
    return float(os.getenv(name, default))


# How many meals one unit of food feeds. ASSUMPTION: FoodFlow planning values.
UNIT_TO_MEALS: Dict[str, float] = {
    "individual_meal": 1,
    "bag": 4,
    "box": 8,
    "tray": 12,
    "half_pan": 10,
    "full_pan": 20,
    "lb": round(1 / 1.2, 4),  # cited: Feeding America, 1.2 lbs per meal
}

# Hours after preparation that food is treated as safe to deliver (safe_until default).
SAFE_UNTIL_HOURS: Dict[str, float] = {"hot": 2, "cold": 4, "frozen": 4, "shelf_stable": 48}

LBS_PER_MEAL = 1.2  # cited: Feeding America
LOAD_WINDOW_MIN = _f("LOAD_WINDOW_MIN", 5)
NO_SHOW_GRACE_MIN = _f("NO_SHOW_GRACE_MIN", 15)
DUPLICATE_WINDOW_MIN = _f("DUPLICATE_WINDOW_MIN", 10)
INTAKE_CONFIRM_DAYS = int(_f("INTAKE_CONFIRM_DAYS", 90))
APPROACHING_WARNING_MIN = _f("APPROACHING_WARNING_MIN", 10)
EXPIRY_WARNING_MIN = _f("EXPIRY_WARNING_MIN", 30)
MATCH_RADIUS_MI = _f("MATCH_RADIUS_MI", 15)
LOADING_MIN = _f("LOADING_MIN", 5)  # time at the pickup curb or counter before departing

# Fallback travel estimate when the routing service is down (per the build spec).
FALLBACK_ROAD_FACTOR = 1.3
FALLBACK_SPEED_KMH = 30.0

# Simulated fleets. ASSUMPTIONS: no real Waymo or robot integration exists.
AV_CAPACITY_MEALS = _f("AV_CAPACITY_MEALS", 60)
AV_SIM_FLEET_SIZE = int(_f("AV_SIM_FLEET_SIZE", 3))
AV_DISPATCH_DELAY_MIN = _f("AV_DISPATCH_DELAY_MIN", 4)
ROBOT_MAX_MI = _f("ROBOT_MAX_MI", 2.0)
ROBOT_CAPACITY_MEALS = _f("ROBOT_CAPACITY_MEALS", 20)
ROBOT_SPEED_MPH = _f("ROBOT_SPEED_MPH", 3.5)
ROBOT_SIM_FLEET_SIZE = int(_f("ROBOT_SIM_FLEET_SIZE", 2))
MEALS_PER_TOTE = _f("MEALS_PER_TOTE", 10)

# Mode selection score (lower is better), in minute-equivalents.
MODE_WEIGHTS = {
    "time": _f("MODE_W_TIME", 1.0),            # minutes from now to arrival
    "margin": _f("MODE_W_MARGIN", 0.5),        # per minute short of a 60 minute safe_until margin
    "reliability": _f("MODE_W_RELIABILITY", 60.0),  # x (1 - observed completion rate)
    "handoff": _f("MODE_W_HANDOFF", 1.0),      # staff minutes needed at the curb
}
SAFE_MARGIN_TARGET_MIN = 60.0
HANDOFF_BURDEN_MIN = {"volunteer": 2.0, "waymo_sim": 6.0, "robot_sim": 6.0}
# Prior completion rate before real trips exist (Laplace-style prior: PRIOR_TRIPS pseudo-trips).
RELIABILITY_PRIOR = {"volunteer": 0.85, "waymo_sim": 0.85, "robot_sim": 0.85}
RELIABILITY_PRIOR_TRIPS = 10

# Tax estimate (IRC 170(e)(3)(C)).
BASIS_ELECTION_FRACTION = 0.25
TAX_INCOME_LIMIT_FRACTION = 0.15
TAX_CARRYFORWARD_YEARS = 5

ASSUMPTIONS: Dict[str, Dict[str, Any]] = {
    "unit_to_meals": {"value": UNIT_TO_MEALS, "kind": "assumption",
                      "note": "Planning conversion from kitchen units to meals. Replace with the restaurant's own counts."},
    "safe_until_hours": {"value": SAFE_UNTIL_HOURS, "kind": "assumption",
                         "note": "Hot 2 h follows USDA FSIS guidance to not leave perishable food out more than 2 hours "
                                 "(1 hour above 90 F); cold/frozen 4 h and shelf-stable 48 h are FoodFlow planning values.",
                         "source": "https://www.fsis.usda.gov/food-safety/safe-food-handling-and-preparation/food-safety-basics/danger-zone-40f-140f"},
    "lbs_per_meal": {"value": LBS_PER_MEAL, "kind": "cited", "note": "Feeding America: 'Each meal is roughly 1.2 pounds'.",
                     "source": "https://www.feedingamerica.org/ways-to-give/faq/about-our-claims"},
    "load_window_min": {"value": LOAD_WINDOW_MIN, "kind": "assumption", "note": "How long a simulated vehicle waits at a curb."},
    "no_show_grace_min": {"value": NO_SHOW_GRACE_MIN, "kind": "assumption", "note": "Minutes past expected arrival before re-queueing."},
    "duplicate_window_min": {"value": DUPLICATE_WINDOW_MIN, "kind": "assumption"},
    "intake_confirm_days": {"value": INTAKE_CONFIRM_DAYS, "kind": "assumption"},
    "fallback_travel": {"value": {"road_factor": FALLBACK_ROAD_FACTOR, "speed_kmh": FALLBACK_SPEED_KMH}, "kind": "assumption",
                        "note": "Used only when the routing service is unavailable; responses are flagged estimated=true."},
    "av_sim": {"value": {"capacity_meals": AV_CAPACITY_MEALS, "fleet_size": AV_SIM_FLEET_SIZE, "dispatch_delay_min": AV_DISPATCH_DELAY_MIN},
               "kind": "assumption", "note": "SIMULATED autonomous vehicle. Not a Waymo integration; no Waymo API is used."},
    "robot_sim": {"value": {"max_mi": ROBOT_MAX_MI, "capacity_meals": ROBOT_CAPACITY_MEALS, "speed_mph": ROBOT_SPEED_MPH,
                            "fleet_size": ROBOT_SIM_FLEET_SIZE}, "kind": "assumption", "note": "SIMULATED sidewalk robot."},
    "meals_per_tote": {"value": MEALS_PER_TOTE, "kind": "assumption"},
    "mode_weights": {"value": MODE_WEIGHTS, "kind": "assumption"},
    "handoff_burden_min": {"value": HANDOFF_BURDEN_MIN, "kind": "assumption"},
    "reliability_prior": {"value": RELIABILITY_PRIOR, "kind": "assumption",
                          "note": f"Blended with observed completion rates as if from {RELIABILITY_PRIOR_TRIPS} prior trips."},
    "tax": {"value": {"basis_election_fraction": BASIS_ELECTION_FRACTION, "income_limit_fraction": TAX_INCOME_LIMIT_FRACTION,
                      "carryforward_years": TAX_CARRYFORWARD_YEARS}, "kind": "cited",
            "note": "IRC 170(e)(3)(C), made permanent by the PATH Act of 2015. Estimates only, not tax advice.",
            "source": "https://www.congress.gov/committee-report/114th-congress/house-report/18"},
}
