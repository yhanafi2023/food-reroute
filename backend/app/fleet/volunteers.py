"""VolunteerProvider (section 6a): the human flow. Only volunteers whose availability,
distance, capacity and equipment fit the food are offered a trip."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Tuple

from sqlalchemy.orm import Session

from app import clients, intake
from app.fleet.base import Cargo, Point, Quote
from app.intelligence.eta.features import haversine_miles
from app.models import Trip, User, VolunteerProfile

EQUIPMENT = {"hot": ("has_insulated_bags", "insulated bags"), "cold": ("has_cooler", "a cooler"),
             "frozen": ("has_cooler", "a cooler")}


class VolunteerProvider:
    mode = "volunteer"
    simulated = False

    def __init__(self, db: Session):
        self.db = db

    def _busy_ids(self) -> set:
        rows = self.db.query(Trip.volunteer_user_id).filter(
            Trip.mode == "volunteer", Trip.status.in_(("matched", "en_route_pickup", "picked_up", "en_route_dropoff"))).all()
        return {r[0] for r in rows}

    def candidates(self, pickup: Point, cargo: Cargo, start_at: datetime, trip_minutes: float,
                   exclude: Iterable[int] = ()) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """Feasible volunteers sorted by pickup ETA, plus counts of why others were not."""
        busy, excluded = self._busy_ids(), set(exclude)
        why = {"unavailable_now": 0, "too_far": 0, "no_equipment": 0, "too_small": 0, "busy": 0, "declined_or_no_show": 0}
        rows = (self.db.query(VolunteerProfile, User).join(User, User.id == VolunteerProfile.user_id)
                .filter(User.active.is_(True)).all())
        near = []
        for v, u in rows:
            if u.id in excluded:
                why["declined_or_no_show"] += 1
                continue
            if u.id in busy:
                why["busy"] += 1
                continue
            dist = haversine_miles(v.home_lat, v.home_lng, pickup[0], pickup[1])
            if dist > v.max_distance_mi:
                why["too_far"] += 1
                continue
            need = EQUIPMENT.get(cargo.category)
            if need and not getattr(v, need[0]):
                why["no_equipment"] += 1
                continue
            if v.capacity_meals < cargo.meals:
                why["too_small"] += 1
                continue
            near.append((v, u, dist))
        if not near:
            return [], why
        mins, est, _ = clients.travel([((v.home_lat, v.home_lng), pickup, 0) for v, _, _ in near])
        out = []
        for (v, u, dist), m in zip(near, mins):
            if not intake.available_at(v.availability or {}, start_at, m["p50"] + trip_minutes):
                why["unavailable_now"] += 1
                continue
            out.append({"user": u, "profile": v, "miles": dist, "pickup_minutes": m["p50"], "estimated": est})
        out.sort(key=lambda c: (c["pickup_minutes"], c["user"].id))
        return out, why

    def availability(self, zone: str = "", window: Tuple[datetime, datetime] = None) -> Dict[str, Any]:
        start = window[0] if window else datetime.utcnow()
        n = sum(1 for v in self.db.query(VolunteerProfile).all() if intake.available_at(v.availability or {}, start))
        return {"mode": self.mode, "simulated": False, "volunteers_available": n}

    def quote(self, pickup: Point, dropoff: Point, cargo: Cargo, start_at: datetime) -> Quote:
        leg, _, _ = clients.travel([(pickup, dropoff, 0)])
        cands, why = self.candidates(pickup, cargo, start_at, leg[0]["p50"])
        if not cands:
            return Quote(False, self.mode, False, reason=describe_unavailable(why))
        c = cands[0]
        eta_pickup = start_at + timedelta(minutes=c["pickup_minutes"])
        return Quote(True, self.mode, False, eta_pickup=eta_pickup, eta_dropoff=eta_pickup + timedelta(minutes=leg[0]["p50"]),
                     carrier_id=c["user"].id, estimated=c["estimated"])

    def dispatch(self, trip: Trip) -> str:
        return f"volunteer:{trip.volunteer_user_id}"

    def status(self, vehicle_id: str) -> Dict[str, Any]:
        return {"vehicle_id": vehicle_id, "simulated": False}

    def cancel(self, trip: Trip) -> None:
        return None


def describe_unavailable(why: Dict[str, int]) -> str:
    parts = {"unavailable_now": "not available at this hour", "too_far": "too far away", "no_equipment": "without the right cooler or bags",
             "too_small": "without enough room", "busy": "on another trip", "declined_or_no_show": "declined or missed this rescue"}
    bits = [f"{n} {parts[k]}" for k, n in why.items() if n]
    return "no volunteer can take it (" + ", ".join(bits) + ")" if bits else "no volunteers registered nearby"
