"""Seeded fleet comparison (section 11): the same fictional Friday evening, two ways.

Runs the REAL posting, matching, mode selection, handoff and failure-handling code
in an isolated in-memory database under a fake clock:
  volunteer_only: every rescue restricted to volunteers
  mixed_fleet:    volunteers plus SIMULATED autonomous vehicles and robots
The people in it are simulated by fixed rules (below), with a fixed random seed,
so every run gives the same numbers. Nothing here touches the real database.

Simulated behavior (assumptions):
  - volunteers accept an offer 2 minutes after it is made; SIM_NO_SHOW_RATE of offers
    (chosen by the seeded random generator) end in a no-show
  - carriers arrive at the ETA the system predicted, pick up, then drive to each stop
    in turn; receiving staff confirm 2 minutes after delivery
  - at a curb, restaurant or org staff unlock and load/unload 2 minutes after the
    vehicle arrives (within the 5 minute window)
"""
from __future__ import annotations

import random
import statistics
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session, sessionmaker

from app import clock, handoff, lifecycle, posting
from app.db import create_schema, make_engine
from app.jobs import run_jobs
from app.models import Organization, Rescue, Trip, User

SEED = 1383
SIM_NO_SHOW_RATE = 0.10
ACCEPT_AFTER_MIN = 2
STAFF_ACTION_MIN = 2
START_LOCAL = datetime(2026, 9, 25, 17, 0)   # a Friday
END_LOCAL = datetime(2026, 9, 26, 3, 0)
POSTS_EVENING, POSTS_LATE = 8, 6              # 5-10 PM, and 10 PM-1 AM when volunteers are scarce


def scenario(restaurants: List[str]) -> List[Dict[str, Any]]:
    rng = random.Random(SEED)
    posts = []
    for n, (lo, hi) in ((POSTS_EVENING, (0, 300)), (POSTS_LATE, (300, 480))):
        for _ in range(n):
            posts.append({"minute": rng.randint(lo, hi), "restaurant": rng.choice(restaurants),
                          "category": rng.choice(["hot", "cold", "cold", "shelf_stable"]),
                          "unit": rng.choice(["bag", "box", "tray", "half_pan"]), "quantity": rng.randint(1, 4)})
    return sorted(posts, key=lambda p: p["minute"])


def run(mode: str) -> Dict[str, Any]:
    from app.seed import seed_accounts

    engine = make_engine("sqlite://")
    create_schema(engine)
    Local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    start = clock.local_to_utc(START_LOCAL)
    end = clock.local_to_utc(END_LOCAL)
    fake = clock.FakeClock(start)
    rng = random.Random(SEED + (0 if mode == "volunteer_only" else 1))
    with clock.use(fake), Local() as db:
        seed_accounts(db)
        db.commit()
        restaurants = [o.name for o in db.query(Organization).filter_by(kind="restaurant").order_by(Organization.id)]
        posts = scenario(restaurants)
        pending_posts = list(posts)
        accepted_at: Dict[int, datetime] = {}
        no_shows: set = set()
        delivered_at: Dict[int, datetime] = {}
        while fake.now() <= end:
            now = fake.now()
            minute = (now - start).total_seconds() / 60
            while pending_posts and pending_posts[0]["minute"] <= minute:
                p = pending_posts.pop(0)
                _post(db, p, mode)
            run_jobs(db, reports=False)
            _act(db, now, rng, accepted_at, no_shows, delivered_at)
            db.commit()
            fake.advance(minutes=1)
        return _metrics(db, start, mode, posts)


def _post(db: Session, p: Dict[str, Any], mode: str) -> None:
    org = db.query(Organization).filter_by(name=p["restaurant"]).one()
    user = db.query(User).filter_by(organization_id=org.id).first()
    body = posting.QuickPost(quantity=p["quantity"], unit=p["unit"], category=p["category"], attested=True,
                             allergens=[], pickup_deadline=clock.now() + timedelta(hours=2))
    rescue = posting.create_post(db, user, body)["rescue"]
    if mode == "volunteer_only":
        rescue.allowed_modes = ["volunteer"]
    from app import dispatch
    dispatch.run_matching(db, rescue, user)


def _staff(db: Session, org_id: int) -> User:
    return db.query(User).filter_by(organization_id=org_id).order_by(User.id).first()


def _act(db: Session, now: datetime, rng: random.Random, accepted_at, no_shows, delivered_at) -> None:
    for trip in db.query(Trip).filter(Trip.status.in_(("matched", "en_route_pickup", "en_route_dropoff", "delivered"))).all():
        rescue = trip.rescue
        if trip.mode == "volunteer":
            vol = trip.volunteer
            if trip.status == "matched" and now >= trip.created_at + timedelta(minutes=ACCEPT_AFTER_MIN):
                if trip.id not in no_shows and rng.random() < SIM_NO_SHOW_RATE:
                    no_shows.add(trip.id)
                if trip.id not in no_shows:
                    lifecycle.set_trip_status(db, trip, "en_route_pickup", vol)
                    accepted_at[trip.id] = now
            elif trip.status == "en_route_pickup" and trip.id not in no_shows and now >= max(trip.eta_pickup_at, accepted_at.get(trip.id, now)):
                meals = sum(s.allocated_meals for s in trip.stops if s.status == "pending")
                lifecycle.pickup(db, trip, rescue.pickup_code, meals, vol)
                trip.route = {**(trip.route or {}), "sim_pickup_at": now.isoformat(), "sim_planned_pickup": trip.eta_pickup_at.isoformat()}
            elif trip.status == "en_route_dropoff":
                shift = timedelta(0)
                if (trip.route or {}).get("sim_pickup_at"):
                    shift = datetime.fromisoformat(trip.route["sim_pickup_at"]) - datetime.fromisoformat(trip.route["sim_planned_pickup"])
                for s in trip.stops:
                    if s.status == "pending" and now >= s.eta_at + shift:
                        lifecycle.deliver_stop(db, s, s.dropoff_code, vol)
                        delivered_at[s.id] = now
                        break
        else:
            if trip.handoff_state == "at_pickup_curb" and now >= trip.load_deadline - timedelta(minutes=5 - STAFF_ACTION_MIN):
                staff = _staff(db, rescue.restaurant_org_id)
                handoff.unlock(db, trip, staff, rescue.pickup_code)
                handoff.loaded(db, trip, staff, sum(s.allocated_meals for s in trip.stops if s.status == "pending"))
            elif trip.handoff_state == "at_dropoff_curb" and now >= trip.unload_deadline - timedelta(minutes=5 - STAFF_ACTION_MIN):
                stop = handoff.current_stop(trip)
                staff = _staff(db, stop.organization_id)
                handoff.unlock(db, trip, staff, stop.dropoff_code)
                handoff.unloaded(db, trip, staff)
                delivered_at[stop.id] = now
        for s in trip.stops:
            if s.status == "delivered" and now >= delivered_at.get(s.id, now) + timedelta(minutes=STAFF_ACTION_MIN):
                staff = _staff(db, s.organization_id)
                p = s.organization.receiver_profile
                lifecycle.receive_stop(db, s, staff, "accepted", None, None, "", 140.0 if rescue.category == "hot" else 38.0,
                                       "Simulated staff", "", p.required_fields or [])
                if trip.mode != "volunteer" and s.status == "received":
                    handoff._set(db, trip, "received", staff)


def _metrics(db: Session, start: datetime, mode: str, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    rescues = db.query(Rescue).order_by(Rescue.id).all()
    delivered, expired, undelivered, minutes, late = 0, 0, 0, [], {"posted": 0, "delivered": 0, "expired": 0}
    by_mode: Dict[str, int] = {}
    for r in rescues:
        got = sum((s.received_meals or 0) for t in r.trips for s in t.stops)
        delivered += got
        posted_local = clock.to_local(r.created_at)
        is_late = posted_local.hour >= 22 or posted_local.hour < 5
        if is_late:
            late["posted"] += r.est_meals
            late["delivered"] += got
        if r.status == "expired":
            expired += r.est_meals
            if is_late:
                late["expired"] += r.est_meals
        elif r.status not in ("received",):
            undelivered += r.est_meals - got
        last = max((s.received_at for t in r.trips for s in t.stops if s.received_at), default=None)
        if last and r.status == "received":
            minutes.append((last - r.created_at).total_seconds() / 60)
        for t in r.trips:
            if t.status == "received":
                by_mode[t.mode] = by_mode.get(t.mode, 0) + sum(s.received_meals or 0 for s in t.stops)
    return {
        "mode": mode, "rescues_posted": len(rescues), "meals_posted": sum(r.est_meals for r in rescues),
        "meals_delivered": delivered, "meals_expired": expired, "meals_not_delivered_other": undelivered,
        "median_minutes_post_to_receipt": round(statistics.median(minutes), 1) if minutes else None,
        "late_night_10pm_to_1am": late, "meals_delivered_by_mode": by_mode,
        "no_show_rate_assumption": SIM_NO_SHOW_RATE,
    }


def compare() -> Dict[str, Any]:
    a, b = run("volunteer_only"), run("mixed_fleet")
    return {
        "scenario": {"seed": SEED, "evening": f"{START_LOCAL:%A %Y-%m-%d} 5 PM to 3 AM (fictional demo network)",
                     "posts_5pm_to_10pm": POSTS_EVENING, "posts_10pm_to_1am": POSTS_LATE},
        "volunteer_only": a, "mixed_fleet": b,
        "difference": {"meals_delivered": b["meals_delivered"] - a["meals_delivered"],
                       "meals_expired": b["meals_expired"] - a["meals_expired"]},
        "label": "SIMULATED: fictional restaurants, orgs and volunteers; simulated vehicles; seeded behavior. "
                 "Numbers come only from running this simulation.",
        "method": __doc__.strip(),
    }

