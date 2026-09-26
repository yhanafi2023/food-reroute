"""Carriers and receiving orgs: offers, handoffs with codes, receipt, re-routing (sections 5, 6d, 7)."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import audit, clock, dispatch, handoff, lifecycle, notify
from app.assumptions import ASSUMPTIONS
from app.auth import ADMIN, ORG_ANY, VOLUNTEER, get_current_user
from app.db import get_db
from app.fleet import geofence
from app.fleet.simulated import SimulatedSidewalkRobotProvider, SimulatedWaymoProvider
from app.fleet.volunteers import VolunteerProvider
from app.models import ReceiverProfile, Trip, TripStop, User, VolunteerProfile
from app.views import rescue_json, stop_json, trip_json

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


@router.post("/trips/{trip_id}/accept")
def accept(trip_id: int, where: Where = Where(), user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    t = _my_trip(db, trip_id, user)
    _location(db, user, where)
    lifecycle.set_trip_status(db, t, "en_route_pickup", user, where.lat, where.lng)
    notify.send(db, db.query(User).filter_by(organization_id=t.rescue.restaurant_org_id, active=True).all(), "matched",
                "Volunteer on the way", f"{user.first_name} accepted rescue #{t.rescue_id}, pickup around "
                f"{clock.fmt_local(t.eta_pickup_at)}.", dedupe=f"accepted:{t.id}")
    db.commit()
    return trip_json(t, user)


@router.post("/trips/{trip_id}/decline")
def decline(trip_id: int, user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    t = _my_trip(db, trip_id, user)
    if t.status != "matched":
        raise HTTPException(409, "Only an offer can be declined; use cancel for an accepted trip")
    lifecycle.end_trip(db, t, "reassigned", user, reason="volunteer declined")
    dispatch.requeue(db, t.rescue, user, "the volunteer declined", exclude_volunteer=user.id)
    db.commit()
    return {"ok": True}


@router.post("/trips/{trip_id}/cancel")
def carrier_cancel(trip_id: int, user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    t = _my_trip(db, trip_id, user)
    if t.status not in ("matched", "en_route_pickup"):
        raise HTTPException(409, "After pickup the food must be delivered; contact the receiving org if there is a problem")
    lifecycle.end_trip(db, t, "reassigned", user, reason="volunteer cancelled")
    dispatch.requeue(db, t.rescue, user, "the volunteer cancelled", exclude_volunteer=user.id)
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
        from app.tax import acks
        acks.on_receipt(db, s)
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

