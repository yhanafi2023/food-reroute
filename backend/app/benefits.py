"""Compliance records (section 9b): California SB 1383 edible food recovery template.

Tax estimates, acknowledgments and the restaurant dashboard live in app/tax/.
RECORDS ONLY. NOT LEGAL OR COMPLIANCE ADVICE.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app import clock
from app.assumptions import LBS_PER_MEAL
from app.models import RecoveryAgreement, Rescue, Trip, TripStop

SB1383_NOTE = "Verify requirements with your local jurisdiction."
CALRECYCLE_GUIDANCE = "https://calrecycle.ca.gov/organics/slcp/foodrecovery/donors"
LBS_SOURCE = "https://www.feedingamerica.org/ways-to-give/faq/about-our-claims"


def _received_stops(db: Session, restaurant_id: int, start: datetime, end: datetime) -> List[TripStop]:
    return (db.query(TripStop).join(Trip, Trip.id == TripStop.trip_id).join(Rescue, Rescue.id == Trip.rescue_id)
            .filter(Rescue.restaurant_org_id == restaurant_id, TripStop.status == "received",
                    TripStop.received_at >= start, TripStop.received_at < end).all())


def sb1383_report(db: Session, restaurant_id: int, month: str) -> Dict[str, Any]:
    """California SB 1383 edible food recovery records for one month (first jurisdiction template)."""
    y, m = map(int, month.split("-"))
    start = clock.local_to_utc(datetime(y, m, 1))
    end = clock.local_to_utc(datetime(y + (m == 12), (m % 12) + 1, 1))
    per_org: Dict[int, Dict[str, Any]] = {}
    for s in _received_stops(db, restaurant_id, start, end):
        org = s.organization
        e = per_org.setdefault(org.id, {"organization": org.name, "address": org.address, "food_types": set(),
                                        "pickups": set(), "meals": 0, "pounds_recovered": 0.0})
        e["food_types"].add(s.trip.rescue.category.replace("_", "-"))
        e["pickups"].add(s.trip_id)
        e["meals"] += s.received_meals or 0
        e["pounds_recovered"] += (s.received_meals or 0) * LBS_PER_MEAL
    agreements = db.query(RecoveryAgreement).filter_by(restaurant_org_id=restaurant_id).all()
    rows = []
    for oid, e in per_org.items():
        rows.append({"organization": e["organization"], "address": e["address"], "food_types": sorted(e["food_types"]),
                     "pickups_in_month": len(e["pickups"]), "meals": e["meals"],
                     "pounds_recovered": round(e["pounds_recovered"], 1),
                     "written_agreements": [{"signed_date": a.signed_date.isoformat(), "document_url": a.document_url}
                                            for a in agreements if a.receiver_org_id == oid]})
    return {"template": "California SB 1383 edible food recovery (commercial edible food generator records)",
            "month": month, "rows": rows,
            "record_items": ["contract or written agreement information", "schedules for donation deliveries or collections",
                             "pounds donated per month for each food recovery organization", "types of food each organization receives"],
            "pounds_method": "meals x 1.2 lbs (Feeding America)", "pounds_source": LBS_SOURCE,
            "guidance": CALRECYCLE_GUIDANCE, "note": SB1383_NOTE}
