"""Demo seed: Miami, near FIU. Loaded when DEMO_MODE=true and the database is empty.

Logins (password demo1234): restaurant@demo.com (ABC Restaurant), driver@demo.com
(Marcus), org@demo.com (Community Food Bank), shelter@demo.com (Hope Shelter),
admin@demo.com. The other demo accounts use the emails listed below.

  python -m app.seed          (from backend/) resets the database to this state
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.db import Base, SessionLocal, engine
from app.models import (
    Delivery, Driver, FoodNeed, FoodRescue, ImpactEvent, Match, MatchStop, Organization, Restaurant, User, utcnow,
)

DEMO_PASSWORD = "demo1234"

# FICTIONAL demo partners. Names and locations are made up for the demo and are kept
# separate from the researched Miami prospects in data/miami_prospects.json.
# name, email, food_category, seats, hist_surplus_rate, lat, lng, address
RESTAURANTS = [
    ("ABC Restaurant", "restaurant@demo.com", "cuban", 90, 0.35, 25.7635, -80.3680, "Demo location near FIU (fictional business)"),
    ("Sunrise Bakery", "bakery@demo.com", "bakery", 40, 0.45, 25.7702, -80.3405, "Demo location near FIU (fictional business)"),
    ("Bayside Buffet", "buffet@demo.com", "buffet", 200, 0.55, 25.7330, -80.3830, "Demo location near FIU (fictional business)"),
    ("Tamiami Pizza", "pizza@demo.com", "pizza", 70, 0.25, 25.7612, -80.3302, "Demo location near FIU (fictional business)"),
    ("Coral Deli", "deli@demo.com", "deli", 50, 0.20, 25.7510, -80.3955, "Demo location near FIU (fictional business)"),
    ("Sweetwater Sushi", "sushi@demo.com", "sushi", 60, 0.10, 25.7790, -80.3760, "Demo location near FIU (fictional business)"),
]
# name, email, lat, lng, capacity_meals, vehicle
DRIVERS = [
    ("Marcus", "driver@demo.com", 25.7580, -80.3720, 80, "SUV"),
    ("Aisha", "aisha@demo.com", 25.7450, -80.3600, 60, "Sedan"),
    ("Diego", "diego@demo.com", 25.7720, -80.3450, 60, "Hatchback"),
    ("Priya", "priya@demo.com", 25.7360, -80.3880, 100, "Minivan"),
    ("Sam", "sam@demo.com", 25.7810, -80.3950, 60, "Sedan"),
]
# name, email, org_type, lat, lng, address, meals_needed, priority, preferred_food, hours_to_deadline
ORGANIZATIONS = [
    ("Community Food Bank", "org@demo.com", "Food bank", 25.7480, -80.3500, "Demo location near FIU (fictional business)", 30, "HIGH", "Any", 6),
    ("Hope Shelter", "shelter@demo.com", "Shelter", 25.7700, -80.3550, "Demo location near FIU (fictional business)", 20, "MEDIUM", "Hot meals", 6),
    ("Westchester Church Pantry", "church@demo.com", "Church pantry", 25.7400, -80.3350, "Demo location near FIU (fictional business)", 25, "LOW", "Any", 8),
    ("FIU Student Pantry", "pantry@demo.com", "School pantry", 25.7545, -80.3790, "Demo location near FIU (fictional business)", 15, "LOW", "Packaged", 8),
]
ADMIN = ("FoodFlow Admin", "admin@demo.com")

# restaurant, driver, organization, meals, lbs, days_ago, minutes: past deliveries (is_demo_seed)
PAST_DELIVERIES = [
    ("Bayside Buffet", "Priya", "Community Food Bank", 45, 54.0, 1, 32),
    ("Sunrise Bakery", "Diego", "Hope Shelter", 24, 18.0, 2, 21),
    ("Tamiami Pizza", "Aisha", "Westchester Church Pantry", 18, 22.5, 3, 26),
]


def seed(db: Session) -> None:
    now = utcnow()
    # One hash shared by every demo account keeps reset under 2 seconds.
    pw = hash_password(DEMO_PASSWORD)

    def user(name: str, email: str, role: str) -> User:
        u = User(name=name, email=email, password_hash=pw, role=role)
        db.add(u)
        db.flush()
        return u

    restaurants = {}
    for name, email, cat, seats, hist, lat, lng, addr in RESTAURANTS:
        r = Restaurant(user_id=user(name, email, "RESTAURANT").id, name=name, address=addr, lat=lat, lng=lng,
                       food_category=cat, seats=seats, hist_surplus_rate=hist, is_demo_seed=True)
        db.add(r)
        restaurants[name] = r
    drivers = {}
    for name, email, lat, lng, cap, vehicle in DRIVERS:
        d = Driver(user_id=user(name, email, "DRIVER").id, name=name, lat=lat, lng=lng, capacity_meals=cap,
                   vehicle=vehicle, is_available=True)
        db.add(d)
        drivers[name] = d
    orgs = {}
    for name, email, otype, lat, lng, addr, meals, prio, pref, hours in ORGANIZATIONS:
        o = Organization(user_id=user(name, email, "ORGANIZATION").id, name=name, org_type=otype, address=addr,
                         lat=lat, lng=lng)
        db.add(o)
        db.flush()
        db.add(FoodNeed(organization_id=o.id, meals_needed=meals, preferred_food=pref, priority=prio,
                        deadline=now + timedelta(hours=hours), status="OPEN"))
        orgs[name] = o
    user(*ADMIN, "ADMIN")
    db.flush()

    # The "expiring soon" rescue: judges see urgency change the match when admin runs matching.
    bakery = restaurants["Sunrise Bakery"]
    db.add(FoodRescue(restaurant_id=bakery.id, food_type="Fresh bread and pastries", meals=20, weight_lbs=15,
                      pickup_address=bakery.address, lat=bakery.lat, lng=bakery.lng,
                      pickup_deadline=now + timedelta(minutes=25), time_sensitivity="HIGH",
                      description="Baked this afternoon. Expiring soon.", status="OPEN", is_demo_seed=True))

    for rname, dname, oname, meals, lbs, days_ago, minutes in PAST_DELIVERIES:
        r, d, o = restaurants[rname], drivers[dname], orgs[oname]
        when = now - timedelta(days=days_ago)
        need = FoodNeed(organization_id=o.id, meals_needed=meals, meals_fulfilled=meals, priority="MEDIUM",
                        deadline=when + timedelta(hours=3), status="FULFILLED", created_at=when - timedelta(hours=1))
        rescue = FoodRescue(restaurant_id=r.id, food_type="Prepared meals", meals=meals, weight_lbs=lbs,
                            pickup_address=r.address, lat=r.lat, lng=r.lng, pickup_deadline=when + timedelta(hours=2),
                            time_sensitivity="MEDIUM", status="CONFIRMED", is_demo_seed=True, created_at=when)
        db.add_all([need, rescue])
        db.flush()
        match = Match(rescue_id=rescue.id, driver_id=d.id, pickup_miles=1.5, dropoff_miles=3.0, eta_minutes=minutes,
                      score=0.0, reasons=["Demo history"], top_candidates=[], status="ACCEPTED", created_at=when)
        match.stops = [MatchStop(need_id=need.id, organization_id=o.id, seq=1, meals=meals,
                                 confirmed_at=when + timedelta(minutes=minutes + 5))]
        db.add(match)
        db.flush()
        delivered = when + timedelta(minutes=minutes)
        delivery = Delivery(
            rescue_id=rescue.id, match_id=match.id, driver_id=d.id, status="CONFIRMED", meals=meals, weight_lbs=lbs,
            route={"geometry": [[r.lat, r.lng], [o.lat, o.lng]], "distance_miles": 3.0, "eta_minutes": minutes,
                   "source": "offline"},
            status_history=[{"status": "CONFIRMED", "at": delivered.isoformat() + "Z"}],
            accepted_at=when, delivered_at=delivered, is_demo_seed=True,
        )
        db.add(delivery)
        db.flush()
        db.add(ImpactEvent(delivery_id=delivery.id, restaurant_id=r.id, organization_id=o.id, meals=meals,
                           weight_lbs=lbs, delivery_minutes=minutes, is_demo_seed=True, created_at=delivered))
    db.commit()


def reset_database() -> None:
    """Drop everything and reseed: the exact demo starting state."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)


def schema_is_current() -> bool:
    """True when every model column exists in the database (new columns need a rebuild)."""
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in tables:
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        if not {c.name for c in table.columns} <= have:
            return False
    return True


def seed_if_empty() -> None:
    """Demo mode startup: rebuild an out-of-date demo database, then seed it if empty."""
    if not schema_is_current():
        reset_database()
        return
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.query(User).first() is None:
            seed(db)


if __name__ == "__main__":
    reset_database()
    print("Database reset to the demo seed.")
