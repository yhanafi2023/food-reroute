"""Server-enforced lifecycle, handoff codes and chain of custody (section 5).

Rescue:  posted -> matched -> en_route_pickup -> picked_up -> en_route_dropoff -> delivered -> received
         exits: cancelled, expired, rejected, reassigned (a rescue returns to posted when re-queued)
Trip:    matched -> en_route_pickup -> picked_up -> en_route_dropoff -> delivered -> received
         exits: cancelled, expired, rejected, reassigned
Stop:    pending -> delivered -> received | rejected   (also rerouted, cancelled)

Illegal transitions raise HTTP 409. Every change writes an audit event.
A rescue's status follows its active trips (the least advanced one), so a split
delivery is 'delivered' only when every trip has delivered.
"""
from __future__ import annotations

import secrets
from typing import Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import audit, clock
from app.assumptions import LBS_PER_MEAL
from app.models import ImpactEvent, Rescue, Trip, TripStop, User

FLOW = ["posted", "matched", "en_route_pickup", "picked_up", "en_route_dropoff", "delivered", "received"]
STAGE = {s: i for i, s in enumerate(FLOW)}
FINAL_RESCUE = ("received", "cancelled", "expired", "rejected")
INACTIVE_TRIP = ("cancelled", "reassigned", "expired")

TRIP_TRANSITIONS = {
    "matched": {"en_route_pickup", "reassigned", "cancelled", "expired"},
    "en_route_pickup": {"picked_up", "reassigned", "cancelled", "expired"},
    "picked_up": {"en_route_dropoff"},
    "en_route_dropoff": {"delivered", "rejected"},  # rejected: no receiving org could take the food
    "delivered": {"received", "rejected"},
}
RESCUE_TRANSITIONS = {
    "posted": {"matched", "cancelled", "expired"},
    "matched": {"en_route_pickup", "posted", "cancelled", "expired", "matched"},
    "en_route_pickup": {"picked_up", "posted", "cancelled", "expired", "en_route_pickup", "matched"},
    "picked_up": {"en_route_dropoff"},
    "en_route_dropoff": {"delivered", "en_route_dropoff", "rejected"},
    "delivered": {"received", "rejected", "delivered", "en_route_dropoff"},
}


def code() -> str:
    return f"{secrets.randbelow(10 ** 4):04d}"


def check_trip_transition(current: str, requested: str) -> None:
    if requested not in TRIP_TRANSITIONS.get(current, set()):
        raise HTTPException(409, f"A trip that is {current.replace('_', ' ')} cannot become {requested.replace('_', ' ')}")


def check_rescue_transition(current: str, requested: str) -> None:
    if requested not in RESCUE_TRANSITIONS.get(current, set()):
        raise HTTPException(409, f"A rescue that is {current.replace('_', ' ')} cannot become {requested.replace('_', ' ')}")


def set_trip_status(db: Session, trip: Trip, to: str, actor: Optional[User], lat=None, lng=None, **details) -> None:
    check_trip_transition(trip.status, to)
    frm = trip.status
    trip.status = to
    if to == "en_route_pickup" and trip.started_at is None:
        trip.started_at = clock.now()
    if to in ("received", "rejected", "cancelled", "reassigned", "expired"):
        trip.finished_at = clock.now()
    audit.log(db, f"trip_{to}", entity="trip", actor=actor, rescue_id=trip.rescue_id, trip_id=trip.id,
              from_state=frm, to_state=to, lat=lat, lng=lng, details=details)
    sync_rescue(db, trip.rescue, actor)


def active_trips(rescue: Rescue) -> List[Trip]:
    """Read fresh from the database: trips created after the rescue was loaded must count."""
    from sqlalchemy.orm import object_session

    db = object_session(rescue)
    trips = db.query(Trip).filter_by(rescue_id=rescue.id).order_by(Trip.id).all() if db else rescue.trips
    return [t for t in trips if t.status not in INACTIVE_TRIP]


def sync_rescue(db: Session, rescue: Rescue, actor: Optional[User] = None) -> None:
    """Move the rescue to the stage of its least advanced active trip."""
    if rescue.status in FINAL_RESCUE:
        return
    trips = active_trips(rescue)
    if not trips:
        target = "posted"
    elif all(t.status in ("received", "rejected") for t in trips):
        target = "rejected" if all(t.status == "rejected" for t in trips) else "received"
    else:
        target = min((t.status for t in trips if t.status in STAGE), key=lambda s: STAGE[s])
    if target != rescue.status:
        frm = rescue.status
        rescue.status = target
        rescue.updated_at = clock.now()
        audit.log(db, f"rescue_{target}", entity="rescue", actor=actor, rescue_id=rescue.id, from_state=frm, to_state=target)


def set_rescue_status(db: Session, rescue: Rescue, to: str, actor: Optional[User], **details) -> None:
    check_rescue_transition(rescue.status, to)
    frm = rescue.status
    rescue.status = to
    rescue.updated_at = clock.now()
    audit.log(db, f"rescue_{to}", entity="rescue", actor=actor, rescue_id=rescue.id, from_state=frm, to_state=to,
              details=details)


def end_trip(db: Session, trip: Trip, to: str, actor: Optional[User], **details) -> None:
    """cancelled / reassigned / expired: close the trip and its open stops."""
    set_trip_status(db, trip, to, actor, **details)
    for s in trip.stops:
        if s.status == "pending":
            s.status = "cancelled"
    if trip.totes_used:
        profile = trip.rescue.restaurant.restaurant_profile
        profile.totes_on_hand += trip.totes_used
        profile.totes_out = max(profile.totes_out - trip.totes_used, 0)
        trip.totes_used = 0


# ---------- handoffs ----------

def pickup(db: Session, trip: Trip, entered_code: str, picked_up_meals: int, actor: User,
           photo_url: str = "", lat=None, lng=None) -> None:
    if trip.status != "en_route_pickup":
        check_trip_transition(trip.status, "picked_up")
    if entered_code != trip.rescue.pickup_code:
        audit.log(db, "pickup_code_rejected", entity="trip", actor=actor, rescue_id=trip.rescue_id, trip_id=trip.id)
        db.commit()  # failed attempts stay in the custody record
        raise HTTPException(400, "That pickup code does not match. Ask the restaurant for the code on their screen.")
    allocated = sum(s.allocated_meals for s in trip.stops if s.status == "pending")
    if picked_up_meals > allocated * 2:
        raise HTTPException(422, f"{picked_up_meals} meals is far more than the {allocated} planned; check the count")
    trip.picked_up_meals = picked_up_meals
    trip.pickup_photo_url = photo_url
    set_trip_status(db, trip, "picked_up", actor, lat, lng, picked_up_meals=picked_up_meals, posted_meals=trip.rescue.est_meals)
    set_trip_status(db, trip, "en_route_dropoff", actor, lat, lng)
    _scale_stops_to_pickup(trip)


def _scale_stops_to_pickup(trip: Trip) -> None:
    """If fewer meals were picked up than planned, the last stops get less (never more than planned)."""
    remaining = trip.picked_up_meals or 0
    for s in trip.stops:
        if s.status != "pending":
            continue
        s.allocated_meals = max(min(s.allocated_meals, remaining), 1) if remaining > 0 else s.allocated_meals
        remaining -= min(s.allocated_meals, remaining)


def deliver_stop(db: Session, stop: TripStop, entered_code: str, actor: User, lat=None, lng=None) -> None:
    trip = stop.trip
    if trip.status != "en_route_dropoff" or stop.status != "pending":
        raise HTTPException(409, f"This drop off is {stop.status} and the trip is {trip.status.replace('_', ' ')}")
    if entered_code != stop.dropoff_code:
        audit.log(db, "dropoff_code_rejected", entity="stop", actor=actor, rescue_id=trip.rescue_id, trip_id=trip.id,
                  stop_id=stop.id)
        db.commit()  # failed attempts stay in the custody record
        raise HTTPException(400, "That drop-off code does not match. Ask the receiving staff for the code on their screen.")
    stop.status, stop.delivered_at = "delivered", clock.now()
    audit.log(db, "stop_delivered", entity="stop", actor=actor, rescue_id=trip.rescue_id, trip_id=trip.id, stop_id=stop.id,
              from_state="pending", to_state="delivered", lat=lat, lng=lng)
    if all(s.status in ("delivered", "received", "rejected", "rerouted", "cancelled") for s in trip.stops):
        set_trip_status(db, trip, "delivered", actor, lat, lng)


def receive_stop(db: Session, stop: TripStop, actor: User, condition: str, received_meals: Optional[int],
                 reject_reason: Optional[str], reject_note: str, temperature_f: Optional[float], received_by_name: str,
                 photo_url: str, required_fields: Iterable[str]) -> None:
    if stop.status != "delivered":
        raise HTTPException(409, f"This drop off is {stop.status}; it can be confirmed only after it is delivered")
    required = set(required_fields or [])
    if "temperature_at_receipt" in required and temperature_f is None:
        raise HTTPException(422, "Your records need the temperature at receipt. Enter it to confirm.")
    if "received_by_name" in required and not received_by_name.strip():
        raise HTTPException(422, "Your records need the name of the person receiving. Enter it to confirm.")
    if condition != "accepted" and not reject_reason:
        raise HTTPException(422, "Say why (temperature, packaging, quantity or other)")
    delivered = stop.allocated_meals
    if condition == "accepted":
        meals = delivered if received_meals is None else received_meals
    elif condition == "partially_accepted":
        if received_meals is None or not 0 < received_meals < delivered:
            raise HTTPException(422, f"For a partial acceptance, enter the meals kept (1 to {delivered - 1})")
        meals = received_meals
    else:
        meals = 0
    stop.condition, stop.reject_reason, stop.reject_note = condition, reject_reason if condition != "accepted" else None, reject_note
    stop.received_meals, stop.temperature_f, stop.received_by_name, stop.photo_url = meals, temperature_f, received_by_name, photo_url
    stop.received_at = clock.now()
    stop.status = "rejected" if condition == "rejected" else "received"
    stop.incomplete_fields = []
    audit.log(db, f"stop_{stop.status}", entity="stop", actor=actor, rescue_id=stop.trip.rescue_id, trip_id=stop.trip_id,
              stop_id=stop.id, from_state="delivered", to_state=stop.status,
              details={"condition": condition, "received_meals": meals, "allocated_meals": delivered,
                       "reject_reason": stop.reject_reason, "temperature_f": temperature_f})
    if meals > 0:
        trip = stop.trip
        db.add(ImpactEvent(delivery_id=trip.id, restaurant_id=trip.rescue.restaurant_org_id, organization_id=stop.organization_id,
                           meals=meals, weight_lbs=round(meals * LBS_PER_MEAL, 1),
                           delivery_minutes=round(((stop.delivered_at or clock.now()) - (trip.started_at or trip.created_at)).total_seconds() / 60, 1),
                           is_demo_seed=trip.rescue.is_fictional))
    from app.tax.service import update_accepted
    update_accepted(db, stop.trip.rescue)
    trip = stop.trip
    final = [s for s in trip.stops if s.status not in ("rerouted", "cancelled")]
    if all(s.status in ("received", "rejected") for s in final):
        set_trip_status(db, trip, "rejected" if all(s.status == "rejected" for s in final) else "received", actor)
