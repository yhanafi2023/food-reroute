"""Analytics for judges and coordinators (section 11). Numbers come only from the database or
from running the seeded simulation (app/fleet_sim.py)."""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
from typing import Any, Dict

from sqlalchemy.orm import Session

from app import clock
from app.eligibility import group
from app.models import MatchingExplanation, Rescue


def coverage(db: Session, include_fictional: bool = True) -> Dict[str, Any]:
    q = db.query(Rescue).filter(Rescue.is_draft.is_(False))
    if not include_fictional:
        q = q.filter(Rescue.is_fictional.is_(False))
    by_hour: Dict[int, Counter] = {h: Counter() for h in range(24)}
    by_mode: Counter = Counter()
    outcome: Counter = Counter()
    for r in q.all():
        h = clock.to_local(r.created_at).hour
        state = "delivered" if r.status == "received" else r.status if r.status in ("expired", "cancelled", "rejected") else "open"
        by_hour[h][state] += 1
        outcome[state] += 1
        for t in r.trips:
            if t.status == "received":
                by_mode[t.mode] += sum(s.received_meals or 0 for s in t.stops)
    return {"by_hour_local": [{"hour": h, **dict(c)} for h, c in by_hour.items() if c],
            "meals_by_mode": dict(by_mode), "rescues_by_outcome": dict(outcome),
            "includes_fictional_demo_data": include_fictional,
            "note": "waymo_sim and robot_sim are simulated vehicles"}


def matching_rejections(db: Session) -> Dict[str, Any]:
    """Why orgs were ineligible, counted once per org per rescue (latest attempt)."""
    latest: Dict[tuple, MatchingExplanation] = {}
    for m in db.query(MatchingExplanation).order_by(MatchingExplanation.attempt).all():
        latest[(m.rescue_id, m.organization_id)] = m
    groups: Counter = Counter()
    codes: Counter = Counter()
    for m in latest.values():
        for g in {group(r["code"]) for r in m.reasons}:
            groups[g] += 1
        for r in m.reasons:
            codes[r["code"]] += 1
    return {"by_reason_group": dict(groups.most_common()), "by_reason_code": dict(codes.most_common()),
            "org_rescue_pairs_evaluated": len(latest),
            "note": "Each count is an organization that could not take a rescue for that reason, from its own intake answers."}


@lru_cache(maxsize=1)
def compare_fleets() -> Dict[str, Any]:
    from app.fleet_sim import compare

    return compare()
