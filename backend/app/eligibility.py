"""Can this organization take this rescue, arriving at this time, by this kind of carrier? (section 4)

Every rule comes from the org's own onboarding answers (Q1 to Q3). Each failed rule
returns a coded, plain-English reason that is stored and shown in
GET /rescues/{id}/matching-explanation.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import clock, intake
from app.models import ReceiverProfile, Rescue, Trip, TripStop

Reason = Dict[str, str]
REASON_GROUP = {
    "onboarding_incomplete": "onboarding",
    "closed": "closed", "closed_exception": "closed", "past_cutoff": "closed",
    "past_safe_until": "food_safety",
    "dietary": "dietary", "allergen": "dietary", "allergens_undeclared": "dietary",
    "capacity": "capacity", "need_met": "capacity",
    "curbside": "curbside", "out_of_range": "distance",
}
DIETARY_NEEDS = {
    "halal_only": ({"halal"}, "halal only"),
    "kosher_only": ({"kosher"}, "kosher only"),
    "vegetarian_only": ({"vegetarian", "vegan"}, "vegetarian only"),
    "vegan_only": ({"vegan"}, "vegan only"),
    "no_pork": ({"no_pork", "halal", "kosher", "vegetarian", "vegan"}, "no pork (the post must say it has no pork)"),
    "no_beef": ({"no_beef", "vegetarian", "vegan"}, "no beef (the post must say it has no beef)"),
}


def _r(code: str, text: str) -> Reason:
    return {"code": code, "text": text}


def meals_committed_today(db: Session, org_id: int) -> int:
    """Meals already on the way to or received by this org since local midnight."""
    local_midnight = clock.local_to_utc(clock.to_local(clock.now()).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None))
    pending = (db.query(func.coalesce(func.sum(TripStop.allocated_meals), 0))
               .join(Trip, Trip.id == TripStop.trip_id)
               .filter(TripStop.organization_id == org_id, TripStop.status.in_(("pending", "delivered")),
                       Trip.status.notin_(("cancelled", "reassigned", "expired"))).scalar())
    received = (db.query(func.coalesce(func.sum(TripStop.received_meals), 0))
                .filter(TripStop.organization_id == org_id, TripStop.status == "received",
                        TripStop.received_at >= local_midnight).scalar())
    return int(pending or 0) + int(received or 0)


def capacity_for(db: Session, p: ReceiverProfile) -> Tuple[int, Optional[Reason]]:
    """How many meals the org can take on this delivery right now (any kind of food)."""
    cap = p.max_meals_per_delivery or 0
    fresh_need = p.current_need is not None and p.current_need_at and clock.now() - p.current_need_at < timedelta(hours=24)
    need = p.current_need if fresh_need else (p.typical_nightly_need or 0)
    remaining_need = need - meals_committed_today(db, p.organization_id)
    if cap <= 0:
        return 0, _r("capacity", "no room for more food right now")
    if remaining_need <= 0:
        return 0, _r("need_met", f"tonight's need ({need} meals) is already covered")
    return min(cap, remaining_need), None


def check(db: Session, p: ReceiverProfile, rescue: Rescue, pickup_at: datetime, arrival_at: datetime,
          mode: str = "any") -> Tuple[List[Reason], int]:
    """(reasons it cannot receive, meals it can take). Empty reasons means eligible."""
    reasons: List[Reason] = []
    if not intake.is_complete(db, p.organization_id):
        return [_r("onboarding_incomplete", "has not given its opening hours and how much food it wants")], 0
    ok, why = intake.receiving_check(db, p, arrival_at)
    if not ok:
        reasons.append(why)
    if arrival_at > rescue.safe_until:
        reasons.append(_r("past_safe_until", f"would arrive after the food's safe-until time ({clock.fmt_local(rescue.safe_until)})"))
    tags = set(rescue.dietary_tags or [])
    for rule in p.dietary_rules or []:
        needed, label = DIETARY_NEEDS[rule]
        if not tags & needed:
            reasons.append(_r("dietary", label))
    refused = set(p.refused_allergens or [])
    if refused:
        if not rescue.allergens_declared:
            reasons.append(_r("allergens_undeclared", f"does not accept food without an allergen list (refuses {', '.join(sorted(refused))})"))
        elif refused & set(rescue.allergens or []):
            reasons.append(_r("allergen", f"does not accept {', '.join(sorted(refused & set(rescue.allergens)))}"))
    if mode in ("waymo_sim", "robot_sim") and not p.curbside_ok:
        reasons.append(_r("curbside", "cannot meet a vehicle at the curb"))
    cap, cap_reason = capacity_for(db, p)
    if cap_reason:
        reasons.append(cap_reason)
    return reasons, cap


def group(code: str) -> str:
    return REASON_GROUP.get(code, code)
