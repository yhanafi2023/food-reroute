"""Impact numbers for the public /impact page and the dashboards.

compute_impact(db) reads the impact_events table, which the backend writes once
per confirmed drop off (a split delivery with two stops writes two rows that
share one delivery_id). The expected columns are:

  delivery_id, restaurant_id, organization_id, meals, weight_lbs,
  delivery_minutes (accepted_at to that drop off), is_demo_seed

Community value is meals x MEAL_VALUE_USD. MEAL_VALUE_USD is an ASSUMPTION set in
the environment, not a measured number. The UI must label it as an estimate.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Iterable, Mapping

from sqlalchemy import text

DEFAULT_MEAL_VALUE_USD = 3.0  # placeholder assumption; set MEAL_VALUE_USD from a sourced figure

IMPACT_EVENTS_QUERY = text(
    "SELECT delivery_id, restaurant_id, organization_id, meals, weight_lbs, delivery_minutes, is_demo_seed "
    "FROM impact_events"
)


def meal_value_usd() -> float:
    try:
        return float(os.getenv("MEAL_VALUE_USD", DEFAULT_MEAL_VALUE_USD))
    except ValueError:
        return DEFAULT_MEAL_VALUE_USD


def summarize_impact(events: Iterable[Mapping[str, Any]], value_per_meal: float) -> Dict[str, Any]:
    """Pure aggregation over impact event rows, so it is testable without a database."""
    meals = 0
    lbs = 0.0
    restaurants = set()
    organizations = set()
    minutes_by_delivery: Dict[Any, float] = {}
    includes_demo = False

    for e in events:
        meals += int(e.get("meals") or 0)
        lbs += float(e.get("weight_lbs") or 0)
        if e.get("restaurant_id") is not None:
            restaurants.add(e["restaurant_id"])
        if e.get("organization_id") is not None:
            organizations.add(e["organization_id"])
        includes_demo = includes_demo or bool(e.get("is_demo_seed"))
        delivery = e.get("delivery_id")
        if delivery is not None:
            # A delivery is finished at its last drop off, so keep the longest time.
            minutes = float(e.get("delivery_minutes") or 0)
            minutes_by_delivery[delivery] = max(minutes_by_delivery.get(delivery, 0.0), minutes)

    timed = [m for m in minutes_by_delivery.values() if m > 0]
    return {
        "meals_rescued": meals,
        "lbs_diverted": round(lbs, 1),
        "deliveries_completed": len(minutes_by_delivery),
        "restaurants": len(restaurants),
        "organizations": len(organizations),
        "avg_delivery_minutes": round(sum(timed) / len(timed), 1) if timed else 0.0,
        "community_value_estimate_usd": round(meals * value_per_meal, 2),
        "includes_demo_data": includes_demo,
    }


def compute_impact(db: Any) -> Dict[str, Any]:
    """Impact contract object from the database. `db` is a SQLAlchemy Session or Connection."""
    rows = db.execute(IMPACT_EVENTS_QUERY).mappings().all()
    return summarize_impact(rows, meal_value_usd())
