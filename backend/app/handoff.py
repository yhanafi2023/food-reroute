"""Contactless curbside handoff for simulated vehicles (section 6d).

vehicle_arriving -> at_pickup_curb (load timer) -> loading -> loaded -> in_transit
-> at_dropoff_curb (unload timer) -> unloaded -> received
No driver carries food: restaurant staff unlock with the pickup code and load;
receiving staff unlock with their drop-off code and unload. The vehicle moves on a
simulated schedule driven by the scheduler (app/jobs.py). Everything is simulated.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import audit, clients, clock, lifecycle, notify
from app.assumptions import LOAD_WINDOW_MIN
from app.models import Trip, TripStop, User


def _require(trip: Trip, *states: str) -> None:
    if trip.mode == "volunteer":
        raise HTTPException(409, "This trip is carried by a volunteer, not a vehicle")
    if trip.handoff_state not in states:
        raise HTTPException(409, f"The vehicle is {str(trip.handoff_state).replace('_', ' ')}, not {' or '.join(s.replace('_', ' ') for s in states)}")


def _set(db: Session, trip: Trip, state: str, actor: Optional[User], **details) -> None:
    frm = trip.handoff_state
    trip.handoff_state = state
    audit.log(db, f"vehicle_{state}", entity="trip", actor=actor, rescue_id=trip.rescue_id, trip_id=trip.id,
              from_state=frm, to_state=state, details={"simulated": True, "vehicle_id": trip.vehicle_id, **details})


def _staff(db: Session, org_id: int):
    return db.query(User).filter_by(organization_id=org_id, active=True).all()


def current_stop(trip: Trip) -> Optional[TripStop]:
    return next((s for s in trip.stops if s.status == "pending"), None)


def arrive_at_pickup(db: Session, trip: Trip) -> None:
    trip.load_deadline = clock.now() + timedelta(minutes=LOAD_WINDOW_MIN)
    _set(db, trip, "at_pickup_curb", None, load_deadline=trip.load_deadline.isoformat())
    prof = trip.rescue.restaurant.restaurant_profile
    notify.send(db, _staff(db, trip.rescue.restaurant_org_id), "vehicle_at_curb", "Simulated vehicle at your curb",
                f"Vehicle {trip.vehicle_id} is at the curb ({prof.pickup_instructions or 'pickup spot'}). "
                f"Unlock with code {trip.rescue.pickup_code} and load within {LOAD_WINDOW_MIN:g} minutes "
                f"(until {clock.fmt_local(trip.load_deadline)}).", dedupe=f"curb-pickup:{trip.id}")


def unlock(db: Session, trip: Trip, user: User, code: str) -> None:
    if trip.handoff_state == "at_pickup_curb":
        if user.organization_id != trip.rescue.restaurant_org_id:
            raise HTTPException(403, "Only the restaurant's staff can unlock the vehicle at pickup")
        if code != trip.rescue.pickup_code:
            raise HTTPException(400, "That unlock code does not match")
        _set(db, trip, "loading", user)
        return
    if trip.handoff_state == "at_dropoff_curb":
        stop = current_stop(trip)
        if stop is None or user.organization_id != stop.organization_id:
            raise HTTPException(403, "Only the receiving organization's staff can unlock the vehicle here")
        if code != stop.dropoff_code:
            raise HTTPException(400, "That unlock code does not match")
        audit.log(db, "vehicle_unlocked_at_dropoff", entity="trip", actor=user, rescue_id=trip.rescue_id, trip_id=trip.id,
                  stop_id=stop.id, details={"simulated": True})
        trip.route = {**(trip.route or {}), "dropoff_unlocked_stop": stop.id}
        return
    _require(trip, "at_pickup_curb", "at_dropoff_curb")


def loaded(db: Session, trip: Trip, user: User, item_count: int, photo_url: str = "") -> None:
    _require(trip, "loading")
    if user.organization_id != trip.rescue.restaurant_org_id:
        raise HTTPException(403, "Only the restaurant's staff can confirm loading")
    _set(db, trip, "loaded", user, item_count=item_count)
    lifecycle.pickup(db, trip, trip.rescue.pickup_code, item_count, user, photo_url)
    stop = current_stop(trip)
    mins, est, _ = clients.travel([((trip.rescue.restaurant.lat, trip.rescue.restaurant.lng),
                                    (stop.organization.lat, stop.organization.lng), 0)])
    stop.eta_at = clock.now() + timedelta(minutes=mins[0]["p50"])
    trip.estimated = trip.estimated or est
    _set(db, trip, "in_transit", None, eta=stop.eta_at.isoformat())


def arrive_at_dropoff(db: Session, trip: Trip) -> None:
    stop = current_stop(trip)
    trip.unload_deadline = clock.now() + timedelta(minutes=LOAD_WINDOW_MIN)
    _set(db, trip, "at_dropoff_curb", None, stop_id=stop.id, unload_deadline=trip.unload_deadline.isoformat())
    p = stop.organization.receiver_profile
    notify.send(db, _staff(db, stop.organization_id), "vehicle_at_curb", "Simulated vehicle at your curb",
                f"Vehicle {trip.vehicle_id} is at {p.curb_location or 'your curb'} with {stop.allocated_meals} meals. "
                f"Unlock with code {stop.dropoff_code} and unload within {LOAD_WINDOW_MIN:g} minutes "
                f"(until {clock.fmt_local(trip.unload_deadline)}).", dedupe=f"curb-dropoff:{trip.id}:{stop.id}")


def unloaded(db: Session, trip: Trip, user: User) -> None:
    _require(trip, "at_dropoff_curb")
    stop = current_stop(trip)
    if stop is None or user.organization_id != stop.organization_id:
        raise HTTPException(403, "Only the receiving organization's staff can confirm unloading")
    if (trip.route or {}).get("dropoff_unlocked_stop") != stop.id:
        raise HTTPException(409, "Unlock the vehicle with your drop-off code first")
    lifecycle.deliver_stop(db, stop, stop.dropoff_code, user)
    _set(db, trip, "unloaded", user, stop_id=stop.id)
