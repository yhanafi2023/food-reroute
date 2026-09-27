"""VolunteerProvider (section 6a): the human flow, shown to people as "drivers". Any driver
who is on the job (weekly schedule or "I'm free now") and within their distance can take a
trip; the kind of food and the driver's equipment or vehicle size play no part."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Tuple

from sqlalchemy.orm import Session

from app import clients, intake
from app.fleet.base import Cargo, Point, Quote
from app.intelligence.eta.features import haversine_miles
from app.models import Trip, User, VolunteerProfile

LIVE_LOCATION_MIN = 30  # a shared GPS fix newer than this replaces the home location for distance and ETA


def origin(v: VolunteerProfile, now: datetime) -> Point:
    """Where the driver starts from: their live location when recent, else home."""
    if v.last_lat is not None and v.last_location_at and now - v.last_location_at <= timedelta(minutes=LIVE_LOCATION_MIN):
        return (v.last_lat, v.last_lng)
    return (v.home_lat, v.home_lng)


def is_available(v: VolunteerProfile, at: datetime, minutes: float = 0) -> bool:
    """Inside the weekly schedule, or switched on with "I'm free now" (available_until)."""
    if v.available_until and at < v.available_until:
        return True
    return intake.available_at(v.availability or {}, at, minutes)


class VolunteerProvider:
    mode = "volunteer"
    simulated = False

    def __init__(self, db: Session, only_user_id: int | None = None):
        self.db = db
        self.only_user_id = only_user_id  # a driver claiming one rescue: nobody else is considered

    def _busy_ids(self) -> set:
        rows = self.db.query(Trip.volunteer_user_id).filter(
            Trip.mode == "volunteer", Trip.status.in_(("matched", "en_route_pickup", "picked_up", "en_route_dropoff"))).all()
        return {r[0] for r in rows}

    def candidates(self, pickup: Point, cargo: Cargo, start_at: datetime, trip_minutes: float,
                   exclude: Iterable[int] = ()) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """Drivers who can take it, sorted by pickup ETA, plus counts of why others cannot."""
        busy, excluded = self._busy_ids(), set(exclude)
        why = {"unavailable_now": 0, "too_far": 0, "busy": 0, "declined_or_no_show": 0}
        rows = (self.db.query(VolunteerProfile, User).join(User, User.id == VolunteerProfile.user_id)
                .filter(User.active.is_(True)).all())
        near = []
        for v, u in rows:
            if self.only_user_id is not None and u.id != self.only_user_id:
                continue
            if u.id in excluded:
                why["declined_or_no_show"] += 1
                continue
            if u.id in busy:
                why["busy"] += 1
                continue
            start = origin(v, start_at)
            dist = haversine_miles(start[0], start[1], pickup[0], pickup[1])
            if dist > v.max_distance_mi:
                why["too_far"] += 1
                continue
            near.append((v, u, dist))
        if not near:
            return [], why
        mins, est, _ = clients.travel([(origin(v, start_at), pickup, 0) for v, _, _ in near])
        out = []
        for (v, u, dist), m in zip(near, mins):
            if not is_available(v, start_at, m["p50"] + trip_minutes):
                why["unavailable_now"] += 1
                continue
            out.append({"user": u, "profile": v, "miles": dist, "pickup_minutes": m["p50"], "estimated": est})
        out.sort(key=lambda c: (c["pickup_minutes"], c["user"].id))
        return out, why

    def availability(self, zone: str = "", window: Tuple[datetime, datetime] = None) -> Dict[str, Any]:
        start = window[0] if window else datetime.utcnow()
        n = sum(1 for v in self.db.query(VolunteerProfile).all() if is_available(v, start))
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
    parts = {"unavailable_now": "not on the job right now", "too_far": "too far away", "busy": "on another trip",
             "declined_or_no_show": "declined or missed this rescue"}
    bits = [f"{n} {parts[k]}" for k, n in why.items() if n]
    return "no driver can take it (" + ", ".join(bits) + ")" if bits else "no drivers registered nearby"
