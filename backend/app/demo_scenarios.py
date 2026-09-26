"""Demo history, produced by running the REAL services under a fake clock (section 12).

Every record these scenarios leave (states, codes, audit trail, notifications) is
the system's own output, on FICTIONAL accounts. They run on the previous evening
(local time) so the history sits in the past:

  1. completed rescue with a full audit trail          (Casa Demo Cocina -> shelter, volunteer)
  2. volunteer no-show that re-queued                   (Demo Pizza Sur, first volunteer never arrives)
  3. partial acceptance                                 (Demo Buffet Oeste, shelter keeps part of it)
  4. late-night simulated AV delivery                   (Demo Grill Norte -> community fridge)
  5. missed simulated-AV load window, volunteer fallback (Demo Grill Norte)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict

from sqlalchemy.orm import Session

from app import clock, dispatch, handoff, lifecycle, posting
from app.jobs import run_jobs
from app.models import Organization, Rescue, Trip, User, VolunteerProfile


def _user(db: Session, org_name: str) -> User:
    org = db.query(Organization).filter_by(name=org_name).one()
    return db.query(User).filter_by(organization_id=org.id).order_by(User.id).first()


def _post(db: Session, org_name: str, menu: str = "", **kw) -> Rescue:
    u = _user(db, org_name)
    if menu:
        from app.models import MenuItem
        kw["menu_item_id"] = db.query(MenuItem).filter_by(organization_id=u.organization_id, name=menu).one().id
    body = posting.QuickPost(attested=True, pickup_deadline=clock.now() + timedelta(minutes=kw.pop("deadline_min", 90)), **kw)
    rescue = posting.create_post(db, u, body)["rescue"]
    dispatch.run_matching(db, rescue, u)
    db.flush()
    return rescue


def _advance(db: Session, fc: clock.FakeClock, minutes: float) -> None:
    fc.advance(minutes=minutes)
    run_jobs(db, reports=False)


def _trips(db: Session, rescue: Rescue, status: str):
    return db.query(Trip).filter_by(rescue_id=rescue.id, status=status).order_by(Trip.id).all()


def _receive(db: Session, fc, trip: Trip, s, receipts) -> None:
    fc.advance(minutes=2)
    staff = db.query(User).filter_by(organization_id=s.organization_id).order_by(User.id).first()
    cond, meals, reason, note = receipts.get(s.organization.name, ("accepted", None, None, ""))
    lifecycle.receive_stop(db, s, staff, cond, meals, reason, note, 145.0 if trip.rescue.category == "hot" else 38.0,
                           staff.first_name, "", s.organization.receiver_profile.required_fields or [])
    if trip.mode != "volunteer" and s.status in ("received", "rejected"):
        handoff._set(db, trip, "received", staff)
    if s.status == "received":
        from app.tax import acks
        acks.on_receipt(db, s)


def complete(db: Session, fc, trip: Trip, receipts=None) -> None:
    """Carry a matched trip to receipt the way people would through the API (volunteer or simulated vehicle)."""
    receipts = receipts or {}
    rescue = trip.rescue
    if trip.mode == "volunteer":
        vol = trip.volunteer
        lifecycle.set_trip_status(db, trip, "en_route_pickup", vol)
        fc.current = max(fc.now(), trip.eta_pickup_at)
        lifecycle.pickup(db, trip, rescue.pickup_code, sum(s.allocated_meals for s in trip.stops), vol)
        for s in list(trip.stops):
            if s.status == "pending":
                fc.current = max(fc.now(), s.eta_at)
                lifecycle.deliver_stop(db, s, s.dropoff_code, vol)
                _receive(db, fc, trip, s, receipts)
        return
    fc.current = max(fc.now(), trip.eta_pickup_at)
    run_jobs(db, reports=False)
    staff = _user(db, rescue.restaurant.name)
    fc.advance(minutes=2)
    handoff.unlock(db, trip, staff, rescue.pickup_code)
    handoff.loaded(db, trip, staff, sum(s.allocated_meals for s in trip.stops if s.status == "pending"))
    stop = handoff.current_stop(trip)
    fc.current = max(fc.now(), stop.eta_at)
    run_jobs(db, reports=False)
    org_staff = db.query(User).filter_by(organization_id=stop.organization_id).order_by(User.id).first()
    fc.advance(minutes=2)
    handoff.unlock(db, trip, org_staff, stop.dropoff_code)
    handoff.unloaded(db, trip, org_staff)
    _receive(db, fc, trip, stop, receipts)


def run_all(db: Session, ids: Dict[str, int]) -> None:
    yesterday = (clock.to_local(clock.now()) - timedelta(days=1)).date()
    midnight = datetime.combine(yesterday, datetime.min.time())
    fc = clock.FakeClock(clock.local_to_utc(midnight + timedelta(hours=18)))
    with clock.use(fc):
        # 1. completed rescue, full audit trail (24 meals to the shelter)
        r1 = _post(db, "Casa Demo Cocina", "Rice and black beans", quantity=2, unit="tray", category="hot",
                   description="Rice, black beans, roast chicken", allergens=[])
        for t in _trips(db, r1, "matched"):
            complete(db, fc, t)

        # 2. the first volunteer never arrives; after the grace period the rescue re-queues
        fc.advance(minutes=20)
        r2 = _post(db, "Demo Pizza Sur", "Garlic knots", quantity=2, unit="box", category="shelf_stable",
                   description="Boxed garlic knots", allergens=["gluten", "dairy"])
        first = _trips(db, r2, "matched")[0]
        fc.current = first.eta_pickup_at
        _advance(db, fc, 16)  # past the no-show grace period: re-queued and re-matched
        for t in _trips(db, r2, "matched"):
            complete(db, fc, t)

        # 3. partial acceptance at the shelter
        fc.advance(minutes=15)
        r3 = _post(db, "Demo Buffet Oeste", "Buffet hot trays", quantity=2, unit="half_pan", category="hot", description="Buffet trays",
                   allergens=["shellfish"])
        for t in _trips(db, r3, "matched"):
            complete(db, fc, t, {"Demo Night Shelter": ("partially_accepted", 12, "packaging", "two pans arrived uncovered")})

        # 4. late-night simulated AV delivery (11:40 PM, cold food to the 24/7 fridge)
        fc.current = clock.local_to_utc(midnight + timedelta(hours=23, minutes=40))
        r4 = _post(db, "Demo Grill Norte", "Salads and wraps", quantity=3, unit="bag", category="cold", description="Salads and wraps", allergens=[])
        for t in _trips(db, r4, "matched") + _trips(db, r4, "en_route_pickup"):
            complete(db, fc, t)

        # 5. the simulated AV's load window is missed; a volunteer who just came online takes over
        fc.advance(minutes=10)
        r5 = _post(db, "Demo Grill Norte", "Sandwich trays", quantity=2, unit="bag", category="cold", description="Sandwich trays", allergens=[])
        av5 = next(t for t in _trips(db, r5, "en_route_pickup") if t.mode == "waymo_sim")
        sam = db.query(User).filter_by(first_name="Sam", role="volunteer").one()
        vp = db.get(VolunteerProfile, sam.id)
        original = dict(vp.availability)
        today, tomorrow = clock.to_local(fc.now()), clock.to_local(fc.now()) + timedelta(days=1)
        vp.availability = {**original, today.strftime("%a").lower(): [["00:00", "24:00"]],
                           tomorrow.strftime("%a").lower(): [["00:00", "02:00"]]}
        fc.current = av5.eta_pickup_at
        run_jobs(db, reports=False)          # vehicle at the curb, load timer starts
        _advance(db, fc, 6)                  # nobody loaded in time: vehicle leaves, volunteer fallback matched
        for t in _trips(db, r5, "matched"):
            complete(db, fc, t)
        vp.availability = original
        db.commit()
