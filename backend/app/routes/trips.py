"""Carriers and receiving orgs: offers, handoffs with codes, receipt, re-routing (sections 5, 6d, 7)."""
from datetime import timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import audit, clock, dispatch, handoff, intake, lifecycle, notify
from app.assumptions import ASSUMPTIONS
from app.auth import ADMIN, ORG_ANY, VOLUNTEER, get_current_user
from app.db import get_db
from app.fleet import geofence
from app.fleet.base import Cargo
from app.fleet.simulated import SimulatedSidewalkRobotProvider, SimulatedWaymoProvider
from app.fleet.volunteers import VolunteerProvider, is_available, origin
from app.intelligence.eta.features import haversine_miles
from app.models import ReceiverProfile, Rescue, Trip, TripStop, User, VolunteerProfile
from app.views import iso, rescue_json, stop_json, trip_json

router = APIRouter(tags=["trips"])


class Where(BaseModel):
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)


class PickupIn(Where):
    code: str = Field(min_length=4, max_length=8)
    picked_up_meals: int = Field(ge=1, le=5000)
    photo_url: str = Field(default="", max_length=500)


class DeliverIn(Where):
    code: str = Field(min_length=4, max_length=8)


class ReceiptIn(BaseModel):
    condition: Literal["accepted", "partially_accepted", "rejected"]
    received_meals: Optional[int] = Field(default=None, ge=0, le=5000)
    reject_reason: Optional[Literal["temperature", "packaging", "quantity", "other"]] = None
    reject_note: str = Field(default="", max_length=300)
    temperature_f: Optional[float] = Field(default=None, ge=-20, le=250)
    received_by_name: str = Field(default="", max_length=120)
    photo_url: str = Field(default="", max_length=500)


class RefuseIn(BaseModel):
    reason: Literal["closed", "full", "schedule_changed"]
    note: str = Field(default="", max_length=300)


def _my_trip(db: Session, trip_id: int, user: User) -> Trip:
    t = db.get(Trip, trip_id)
    if t is None or t.volunteer_user_id != user.id:
        raise HTTPException(404, "Trip not found")
    return t


def _org_stop(db: Session, stop_id: int, user: User) -> TripStop:
    s = db.get(TripStop, stop_id)
    if s is None or s.organization_id != user.organization_id:
        raise HTTPException(404, "Delivery not found")
    return s


def _vol_stop(db: Session, stop_id: int, user: User) -> TripStop:
    s = db.get(TripStop, stop_id)
    if s is None or s.trip.volunteer_user_id != user.id:
        raise HTTPException(404, "Stop not found")
    return s


def _location(db: Session, user: User, where: Where) -> None:
    if where.lat is not None and where.lng is not None:
        vp = db.get(VolunteerProfile, user.id)
        vp.last_lat, vp.last_lng, vp.last_location_at = where.lat, where.lng, clock.now()


# ---------- volunteers ----------

@router.get("/volunteers/me/trips")
def my_trips(user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    trips = db.query(Trip).filter_by(volunteer_user_id=user.id).order_by(Trip.id.desc()).limit(50).all()
    return {"offers": [trip_json(t, user) for t in trips if t.status == "matched"],
            "active": [trip_json(t, user) for t in trips if t.status in ("en_route_pickup", "picked_up", "en_route_dropoff", "delivered")],
            "history": [trip_json(t, user) for t in trips if t.status in ("received", "rejected", "cancelled", "reassigned", "expired")]}


@router.get("/trips/{trip_id}")
def get_trip(trip_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.get(Trip, trip_id)
    if t is None:
        raise HTTPException(404, "Trip not found")
    if user.role == "admin" or t.volunteer_user_id == user.id or user.organization_id == t.rescue.restaurant_org_id:
        return trip_json(t, user)
    if user.role in ("org_staff", "org_manager") and any(s.organization_id == user.organization_id for s in t.stops):
        return trip_json(t, user, only_org=user.organization_id)
    raise HTTPException(404, "Trip not found")


def _accept(db: Session, t: Trip, user: User, where: Where) -> None:
    _location(db, user, where)
    lifecycle.set_trip_status(db, t, "en_route_pickup", user, where.lat, where.lng)
    notify.send(db, db.query(User).filter_by(organization_id=t.rescue.restaurant_org_id, active=True).all(), "matched",
                "Driver on the way", f"{user.first_name} accepted rescue #{t.rescue_id}, pickup around "
                f"{clock.fmt_local(t.eta_pickup_at)}.", dedupe=f"accepted:{t.id}")


@router.post("/trips/{trip_id}/accept")
def accept(trip_id: int, where: Where = Where(), user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    t = _my_trip(db, trip_id, user)
    _accept(db, t, user, where)
    db.commit()
    return trip_json(t, user)


# ---------- finding work: "I'm free now", open rescues nearby, claim one ----------

YOUR_REASON = {"too_far": "it is farther than your maximum distance",
               "unavailable_now": "you are not on the job right now"}


class FreeNowIn(Where):
    minutes: int = Field(ge=0, le=12 * 60, description="0 turns it off")


def _busy(db: Session, user: User) -> bool:
    return db.query(Trip).filter(Trip.volunteer_user_id == user.id,
                                 Trip.status.in_(("matched", "en_route_pickup", "picked_up", "en_route_dropoff"))).first() is not None


def _open_rescues(db: Session) -> List[Rescue]:
    now = clock.now()
    return (db.query(Rescue).filter(Rescue.status == "posted", Rescue.is_draft.is_(False), Rescue.pickup_deadline > now,
                                    Rescue.safe_until > now).order_by(Rescue.pickup_deadline).all())


def _availability_json(v: VolunteerProfile) -> dict:
    now = clock.now()
    free = v.available_until if v.available_until and v.available_until > now else None
    return {"available_until": iso(free) if free else None,
            "on_schedule_now": intake.available_at(v.availability or {}, now),
            "available_now": is_available(v, now)}


@router.get("/volunteers/me/availability")
def my_availability(user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    return _availability_json(db.get(VolunteerProfile, user.id))


@router.post("/volunteers/me/availability")
def set_free_now(body: FreeNowIn, user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    """Switch "I'm free now" on for `minutes` (or off with 0). Switching on offers the most urgent
    open rescue this driver can take straight away, instead of waiting for the next job run."""
    v = db.get(VolunteerProfile, user.id)
    _location(db, user, body)
    v.available_until = clock.now() + timedelta(minutes=body.minutes) if body.minutes else None
    offered = None
    if body.minutes and not _busy(db, user):
        for rescue in _open_rescues(db):
            if dispatch.run_matching(db, rescue, user, only_volunteer=user.id).get("matched"):
                offered = rescue.id
                break
    audit.log(db, "volunteer_free_now" if body.minutes else "volunteer_free_off", entity="user", actor=user,
              details={"minutes": body.minutes, "offered_rescue": offered})
    db.commit()
    return {**_availability_json(v), "offered_rescue_id": offered}


@router.get("/volunteers/me/open-rescues")
def open_rescues(user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    """Posted rescues nobody has taken yet, nearest first. A driver can take any of them within their distance."""
    v = db.get(VolunteerProfile, user.id)
    here = origin(v, clock.now())
    out = []
    for r in _open_rescues(db):
        miles = haversine_miles(here[0], here[1], r.restaurant.lat, r.restaurant.lng)
        if miles > max(v.max_distance_mi, 1) * 2:
            continue
        problems = []
        if miles > v.max_distance_mi:
            problems.append(f"{miles:.1f} mi away, past your {v.max_distance_mi:g} mi limit")
        out.append({"id": r.id, "restaurant": {"name": r.restaurant.name, "address": r.restaurant.address,
                                               "lat": r.restaurant.lat, "lng": r.restaurant.lng},
                    "est_meals": r.est_meals, "description": r.description,
                    "allergens": r.allergens or [], "pickup_deadline": iso(r.pickup_deadline),
                    "miles": round(miles, 1), "can_take": not problems, "problems": problems})
    out.sort(key=lambda o: (not o["can_take"], o["miles"]))
    return {"rescues": out, "busy": _busy(db, user), **_availability_json(v)}


@router.post("/volunteers/me/open-rescues/{rescue_id}/claim")
def claim(rescue_id: int, where: Where = Where(), user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    """Take an open rescue: match it to this driver only and accept it in one step."""
    rescue = db.get(Rescue, rescue_id)
    if rescue is None or rescue.is_draft:
        raise HTTPException(404, "Rescue not found")
    if _busy(db, user):
        raise HTTPException(409, "Finish or cancel your current trip before taking another one")
    if rescue.status != "posted":
        raise HTTPException(409, "Someone else already took this rescue")
    _location(db, user, where)
    v = db.get(VolunteerProfile, user.id)
    soon = clock.now() + timedelta(hours=2)
    if not v.available_until or v.available_until < soon:
        v.available_until = soon  # taking a job means being free for it
    fits, why = VolunteerProvider(db, only_user_id=user.id).candidates(
        (rescue.restaurant.lat, rescue.restaurant.lng), Cargo(rescue.est_meals), clock.now(), 0)
    if not fits:
        db.commit()
        reasons = [YOUR_REASON[k] for k, n in why.items() if n and k in YOUR_REASON]
        raise HTTPException(409, "You can't take this rescue: " + ("; ".join(reasons) or "it is not open to you"))
    result = dispatch.run_matching(db, rescue, user, only_volunteer=user.id)
    trip = db.query(Trip).filter_by(rescue_id=rescue.id, volunteer_user_id=user.id, status="matched").first()
    if not result.get("matched") or trip is None:
        db.commit()  # keep the matching explanation for the restaurant and admins
        why = result.get("why") or result.get("reason", "it cannot be matched right now")
        raise HTTPException(409, f"You can't take this rescue: {why}")
    _accept(db, trip, user, where)
    db.commit()
    return trip_json(trip, user)


@router.post("/trips/{trip_id}/decline")
def decline(trip_id: int, user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    t = _my_trip(db, trip_id, user)
    if t.status != "matched":
        raise HTTPException(409, "Only an offer can be declined; use cancel for an accepted trip")
    lifecycle.end_trip(db, t, "reassigned", user, reason="driver declined")
    dispatch.requeue(db, t.rescue, user, "the driver declined", exclude_volunteer=user.id)
    db.commit()
    return {"ok": True}


@router.post("/trips/{trip_id}/cancel")
def carrier_cancel(trip_id: int, user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    t = _my_trip(db, trip_id, user)
    if t.status not in ("matched", "en_route_pickup"):
        raise HTTPException(409, "After pickup the food must be delivered; contact the receiving org if there is a problem")
    lifecycle.end_trip(db, t, "reassigned", user, reason="driver cancelled")
    dispatch.requeue(db, t.rescue, user, "the driver cancelled", exclude_volunteer=user.id)
    db.commit()
    return {"ok": True}


@router.post("/trips/{trip_id}/pickup")
def pickup(trip_id: int, body: PickupIn, user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    t = _my_trip(db, trip_id, user)
    _location(db, user, body)
    lifecycle.pickup(db, t, body.code, body.picked_up_meals, user, body.photo_url, body.lat, body.lng)
    notify.send(db, db.query(User).filter_by(organization_id=t.rescue.restaurant_org_id, active=True).all(), "picked_up",
                "Food picked up", f"{body.picked_up_meals} meals picked up by {user.first_name}.", dedupe=f"picked:{t.id}")
    db.commit()
    return trip_json(t, user)


@router.post("/stops/{stop_id}/deliver")
def deliver(stop_id: int, body: DeliverIn, user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    s = _vol_stop(db, stop_id, user)
    _location(db, user, body)
    lifecycle.deliver_stop(db, s, body.code, user, body.lat, body.lng)
    notify.send(db, db.query(User).filter_by(organization_id=s.organization_id, active=True).all(), "delivered",
                "Food delivered", f"{s.allocated_meals} meals delivered. Please confirm receipt.", dedupe=f"delivered:{s.id}")
    db.commit()
    return trip_json(s.trip, user)


@router.post("/stops/{stop_id}/report-closed")
def report_closed(stop_id: int, body: RefuseIn, user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    """The carrier arrived and the org is closed or full: re-route to the next eligible org."""
    s = _vol_stop(db, stop_id, user)
    if s.status != "pending" or s.trip.status != "en_route_dropoff":
        raise HTTPException(409, "Only a pending drop off on the way can be re-routed")
    new = dispatch.reroute_stop(db, s, user, f"{s.organization.name} was {body.reason.replace('_', ' ')} on arrival")
    db.commit()
    return {"rerouted_to": stop_json(new, user) if new else None, "trip": trip_json(s.trip, user)}


@router.patch("/volunteers/me/location")
def share_location(body: Where, user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    if body.lat is None or body.lng is None:
        raise HTTPException(422, "Send lat and lng")
    _location(db, user, body)
    db.commit()
    return {"ok": True}


# ---------- receiving orgs ----------

@router.get("/orgs/me/deliveries")
def org_deliveries(user: User = Depends(ORG_ANY), db: Session = Depends(get_db)):
    stops = (db.query(TripStop).filter_by(organization_id=user.organization_id).order_by(TripStop.id.desc()).limit(100).all())
    out = {"incoming": [], "to_confirm": [], "history": []}
    for s in stops:
        item = {"stop": stop_json(s, user), "rescue": rescue_json(s.trip.rescue, user, only_org=user.organization_id)}
        key = "incoming" if s.status == "pending" else "to_confirm" if s.status == "delivered" else "history"
        out[key].append(item)
    return out


@router.get("/stops/{stop_id}/receipt-form")
def receipt_form(stop_id: int, user: User = Depends(ORG_ANY), db: Session = Depends(get_db)):
    s = _org_stop(db, stop_id, user)
    p = db.get(ReceiverProfile, user.organization_id)
    previous = (db.query(TripStop).filter(TripStop.organization_id == user.organization_id, TripStop.id != s.id)
                .all())
    missing = sorted({f for x in previous for f in (x.incomplete_fields or [])})
    return {"stop": stop_json(s, user), "required_fields": p.required_fields or [],
            "prompt": ("Earlier deliveries are missing: " + ", ".join(missing) + ". Please capture them this time.") if missing else None}


@router.post("/stops/{stop_id}/receipt")
def confirm_receipt(stop_id: int, body: ReceiptIn, user: User = Depends(ORG_ANY), db: Session = Depends(get_db)):
    s = _org_stop(db, stop_id, user)
    p = db.get(ReceiverProfile, user.organization_id)
    lifecycle.receive_stop(db, s, user, body.condition, body.received_meals, body.reject_reason, body.reject_note,
                           body.temperature_f, body.received_by_name, body.photo_url, p.required_fields or [])
    if s.trip.mode != "volunteer" and s.status in ("received", "rejected"):
        handoff._set(db, s.trip, "received", user, stop_id=s.id)
    if s.status == "received":
        from app import benefits
        benefits.create_acknowledgment(db, s)
    people = db.query(User).filter_by(organization_id=s.trip.rescue.restaurant_org_id, active=True).all()
    if s.trip.volunteer:
        people.append(s.trip.volunteer)
    notify.send(db, people, "receipt_confirmed", "Receipt confirmed",
                f"{s.organization.name} {body.condition.replace('_', ' ')} {s.received_meals} of {s.allocated_meals} meals.",
                dedupe=f"receipt:{s.id}")
    db.commit()
    return stop_json(s, user)


@router.post("/stops/{stop_id}/refuse")
def refuse(stop_id: int, body: RefuseIn, user: User = Depends(ORG_ANY), db: Session = Depends(get_db)):
    """The org closed, is full, or changed its schedule before the food arrived."""
    s = _org_stop(db, stop_id, user)
    if s.status != "pending":
        raise HTTPException(409, "Only a drop off that has not arrived yet can be refused; use receipt to reject delivered food")
    new = dispatch.reroute_stop(db, s, user, f"{s.organization.name} is {body.reason.replace('_', ' ')}")
    db.commit()
    return {"rerouted": new is not None}


@router.post("/stops/{stop_id}/meals-served")
def meals_served(stop_id: int, meals: int, user: User = Depends(ORG_ANY), db: Session = Depends(get_db)):
    s = _org_stop(db, stop_id, user)
    if s.status != "received" or meals < 0 or meals > (s.received_meals or 0):
        raise HTTPException(422, f"Enter 0 to {s.received_meals or 0} meals served from this delivery")
    s.meals_served = meals
    audit.log(db, "meals_served_recorded", entity="stop", actor=user, rescue_id=s.trip.rescue_id, stop_id=s.id,
              details={"meals": meals})
    db.commit()
    return {"stop_id": s.id, "meals_served": meals}


# ---------- simulated vehicle curbside handoff ----------

class UnlockIn(BaseModel):
    code: str = Field(min_length=4, max_length=8)


class LoadedIn(BaseModel):
    item_count: int = Field(ge=1, le=5000)
    photo_url: str = Field(default="", max_length=500)


def _vehicle_trip(db: Session, trip_id: int, user: User) -> Trip:
    t = db.get(Trip, trip_id)
    allowed = t is not None and (user.organization_id == t.rescue.restaurant_org_id or
                                 any(s.organization_id == user.organization_id for s in t.stops))
    if not allowed:
        raise HTTPException(404, "Trip not found")
    return t


@router.post("/trips/{trip_id}/curb/unlock")
def curb_unlock(trip_id: int, body: UnlockIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = _vehicle_trip(db, trip_id, user)
    handoff.unlock(db, t, user, body.code)
    db.commit()
    return trip_json(t, user)


@router.post("/trips/{trip_id}/curb/loaded")
def curb_loaded(trip_id: int, body: LoadedIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = _vehicle_trip(db, trip_id, user)
    handoff.loaded(db, t, user, body.item_count, body.photo_url)
    db.commit()
    return trip_json(t, user)


@router.post("/trips/{trip_id}/curb/unloaded")
def curb_unloaded(trip_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = _vehicle_trip(db, trip_id, user)
    handoff.unloaded(db, t, user)
    db.commit()
    return trip_json(t, user, only_org=user.organization_id)


# ---------- fleet, config, jobs ----------

@router.get("/fleet/availability")
def fleet_availability(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = clock.now()
    return {"providers": [VolunteerProvider(db).availability("", (now, now)), SimulatedWaymoProvider(db).availability(),
                          SimulatedSidewalkRobotProvider(db).availability()],
            "zone": {k: v for k, v in geofence.zone().items() if k != "ring"},
            "note": "Autonomous vehicles and robots are SIMULATED. No Waymo or robot API is used."}


@router.get("/config/assumptions")
def assumptions():
    return ASSUMPTIONS


@router.post("/admin/jobs/run")
def run_jobs(user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    from app.jobs import run_jobs as run

    return run(db)

