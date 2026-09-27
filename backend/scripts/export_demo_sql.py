"""Build a realistic, FICTIONAL demo dataset and write it as Postgres SQL for Supabase.

  cd backend
  python -m scripts.export_demo_sql you@example.com "Your Name" [--days 30] [--out ../demo_data.sql]

Everything runs through the app's real services (posting, matching, pickup, delivery, receipt)
under a fake clock, on a throwaway SQLite database, so every rescue, trip, code, receipt and
audit event is consistent; the rows are then dumped as INSERTs. The SQL file TRUNCATES every
table first, so it replaces whatever the target database holds (including your admin account,
which it re-creates with the email and name given here).

Every account gets the password typed at the prompt (or DEMO_SQL_PASSWORD, for automation) and
is a normal account, not a DEMO_MODE-only one, so it signs in on a production deploy. Orgs and
rescues keep is_fictional=true so they stay easy to find and remove.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import random
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

# A throwaway SQLite database and no outside services: set before any app import reads the config.
_TMP = Path(tempfile.mkdtemp(prefix="foodflow-demo-")) / "demo.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP.as_posix()}"
os.environ["DEMO_MODE"] = "true"
os.environ["RUN_SCHEDULER"] = "false"
os.environ["ROUTING_PROVIDER"] = "offline"
for _k in ("ROUTING_SERVICE_URL", "ALLOCATION_SERVICE_URL", "SMTP_HOST", "TWILIO_ACCOUNT_SID", "SUPABASE_URL"):
    os.environ[_k] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import clock, intake  # noqa: E402
from app.auth import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, hash_password  # noqa: E402
from app.db import Base, SessionLocal, create_schema, engine  # noqa: E402
from app.demo_scenarios import _post, _trips, complete  # noqa: E402
from app.jobs import run_jobs  # noqa: E402
from app.models import Organization, ReceiverProfile, RestaurantProfile, User, VolunteerProfile  # noqa: E402

DAYS = intake.WEEKDAYS
EVERY_DAY = lambda windows: {d: windows for d in DAYS}  # noqa: E731
# bookkeeping, plus notification inboxes (the bulkiest table, and nothing reads them back for a demo)
SKIP_TABLES = {"login_attempts", "job_locks", "idempotency_records", "notifications"}

# name, lat, lng, closing, staffed_until, totes, fmv/meal, basis/meal, 25% election, surplus usually,
# (manager, staff), menu: (description, unit, quantity range, allergens, dietary tags)
RESTAURANTS = [
    ("Casa Luna Cocina", 25.7630, -80.3690, "22:00", "23:30", 6, 9.0, 3.0, False, "after dinner service, 9:30 to 10 PM",
     ("Luis Ferrer", "Rosa Delgado"),
     [("Rice, black beans and roast chicken", "tray", (2, 4), [], []),
      ("Picadillo with white rice", "half_pan", (2, 3), [], ["contains_beef"]),
      ("Sweet plantains and yellow rice", "tray", (1, 3), [], ["vegetarian"]),
      ("Cuban sandwiches, halved", "box", (2, 4), ["gluten", "dairy"], ["contains_pork"])]),
    ("Sunrise Bakehouse", 25.7700, -80.3450, "20:00", "21:00", 2, 4.0, None, True, "at closing, 8 PM",
     ("Hannah Weiss", "Tyler Brooks"),
     [("Day-old bagels and rolls", "bag", (3, 6), ["gluten", "sesame"], ["vegetarian"]),
      ("Croissants and muffins", "box", (2, 4), ["gluten", "dairy", "eggs"], ["vegetarian"]),
      ("Whole wheat sandwich loaves", "bag", (2, 5), ["gluten"], ["vegan"])]),
    ("Northside Grill", 25.7930, -80.3500, "00:00", "01:00", 4, 11.0, 4.0, False, "late night, 11 PM to midnight",
     ("Derek Collins", "Maya Johnson"),
     [("Grilled chicken wraps", "bag", (2, 4), ["gluten"], []),
      ("Garden salads with dressing on the side", "bag", (2, 3), [], ["vegetarian"]),
      ("Burger patties and buns", "tray", (1, 3), ["gluten"], ["contains_beef"])]),
    ("Coral Pizza Co.", 25.7350, -80.3600, "22:00", "22:30", 0, 3.5, 1.2, False, "at closing",
     ("Anthony Russo", "Bella Marino"),
     [("Cheese and veggie pizzas", "box", (3, 6), ["gluten", "dairy"], ["vegetarian"]),
      ("Boxed garlic knots", "box", (2, 4), ["gluten", "dairy"], ["vegetarian"])]),
    ("Westend Buffet", 25.7580, -80.4000, "23:00", "00:30", 8, 7.0, 2.5, False, "after the 10 PM buffet close",
     ("Kenji Watanabe", "Carla Mendes"),
     [("Buffet trays: lo mein and vegetables", "half_pan", (2, 4), ["gluten", "soy"], ["vegetarian"]),
      ("Buffet trays: fried rice and chicken", "full_pan", (1, 2), ["soy", "eggs"], []),
      ("Shrimp and vegetable stir-fry", "half_pan", (1, 2), ["shellfish", "soy"], [])]),
    ("Palm Leaf Thai Kitchen", 25.7505, -80.3405, "22:00", "22:30", 3, 10.0, 3.5, False, "after 9:30 PM",
     ("Nok Srisai", "Ben Carter"),
     [("Pad thai with tofu", "tray", (2, 3), ["peanuts", "soy", "eggs"], ["vegetarian"]),
      ("Green curry and jasmine rice", "half_pan", (1, 3), [], []),
      ("Fresh spring rolls", "box", (2, 3), ["soy"], ["vegan"])]),
    ("Mango Tree Cafe", 25.7665, -80.3820, "21:00", "21:30", 2, 8.0, 2.8, False, "at closing, 9 PM",
     ("Sofia Reyes", "Jordan Lee"),
     [("Black bean and quinoa bowls", "individual_meal", (10, 20), [], ["vegan"]),
      ("Turkey and avocado sandwiches", "individual_meal", (8, 16), ["gluten"], []),
      ("Lentil soup", "half_pan", (1, 2), [], ["vegan"])]),
    ("Harbor Poke Bar", 25.7440, -80.3710, "21:30", "22:00", 2, 12.0, 4.5, False, "after 9 PM",
     ("Kai Nakamura", "Leilani Park"),
     [("Salmon poke bowls", "individual_meal", (6, 14), ["fish", "soy", "sesame"], []),
      ("Tofu poke bowls", "individual_meal", (5, 10), ["soy", "sesame"], ["vegan"])]),
    ("Bluebird Diner", 25.7800, -80.3620, "23:00", "23:30", 4, 8.5, 3.0, False, "late evening",
     ("Frank Donnelly", "Erin Walsh"),
     [("Mac and cheese", "half_pan", (1, 3), ["gluten", "dairy"], ["vegetarian"]),
      ("Meatloaf and mashed potatoes", "tray", (2, 3), ["dairy", "eggs"], ["contains_beef"]),
      ("Frozen pancake packs", "bag", (2, 4), ["gluten", "dairy", "eggs"], ["vegetarian"])]),
    ("Green Fork Salads", 25.7560, -80.3530, "20:30", "21:00", 2, 9.5, 3.2, False, "at closing, 8:30 PM",
     ("Olivia Grant", "Marcus Hale"),
     [("Kale caesar salads", "individual_meal", (8, 16), ["dairy", "eggs", "fish"], ["vegetarian"]),
      ("Mediterranean grain bowls", "individual_meal", (8, 14), ["sesame"], ["vegan", "halal"])]),
]

# receivers: intake answers (Q1 receiving, Q2 food, Q3 records) as in app/seed.py, (manager, staff)
RECEIVERS = {
    "Westchester Community Food Bank": dict(
        lat=25.7480, lng=-80.3500, legal="Westchester Community Food Bank Inc. (fictional)", people=("Patricia Moore", "Andre Jackson"),
        q1=dict(schedule={**{d: [["08:00", "17:00"]] for d in DAYS[:5]}, "sat": [["09:00", "13:00"]], "sun": []},
                cutoff_minutes=30, receiving_contact_name="Andre Jackson", receiving_contact_phone="305-555-0101",
                receiving_instructions="Loading dock at the back, ring the bell.", curbside_ok=True,
                curb_location="Loading dock driveway"),
        q2=dict(dietary_rules=[], refused_allergens=[],
                max_meals_per_delivery=150, typical_nightly_need=100),
        q3=dict(required_fields=["date_time", "donor_name", "donor_address", "food_description",
                                 "quantity_meals", "weight_lbs"],
                report_frequency="monthly", report_format="csv", reports_to="Regional food bank network (fictional)",
                is_501c3=True, ein="00-0000001"),
        verified=True),
    "Safe Harbor Night Shelter": dict(
        lat=25.7700, lng=-80.3550, legal="Safe Harbor Night Shelter Corp. (fictional)", people=("Grace Thompson", "Tomas Rivera"),
        q1=dict(schedule=EVERY_DAY([["16:00", "24:00"]]), cutoff_minutes=15,
                receiving_contact_name="Tomas Rivera", receiving_contact_phone="305-555-0102",
                receiving_instructions="Side door on the east wall, doorbell.", curbside_ok=True,
                curb_location="East side door, loading zone"),
        q2=dict(dietary_rules=[], refused_allergens=[], max_meals_per_delivery=80, typical_nightly_need=60),
        q3=dict(required_fields=["date_time", "donor_name", "food_description", "quantity_meals",
                                 "condition", "received_by_name"],
                report_frequency="per_delivery", report_format="pdf", reports_to="City homeless services program (fictional)",
                is_501c3=True, ein="00-0000002"),
        verified=True),
    "Neighbors Community Fridge": dict(
        lat=25.7545, lng=-80.3790, legal="Neighbors Community Fridge Collective (fictional)", people=("Jasmine Ortiz", "Eli Novak"),
        q1=dict(schedule=EVERY_DAY([["00:00", "24:00"]]), cutoff_minutes=0,
                receiving_contact_name="Fridge steward on call", receiving_contact_phone="305-555-0103",
                receiving_instructions="Fridge is outside by the front gate; label with date.", curbside_ok=True,
                curb_location="Front gate"),
        q2=dict(dietary_rules=[], refused_allergens=[], max_meals_per_delivery=40,
                typical_nightly_need=30),
        q3=dict(required_fields=["date_time", "food_description", "quantity_meals"], report_frequency="weekly",
                report_format="csv", reports_to="", is_501c3=False, ein=None),
        verified=False),
    "Crescent Halal Pantry": dict(
        lat=25.7400, lng=-80.3350, legal="Crescent Halal Pantry (fictional)", people=("Yusuf Rahman", "Amina Saleh"),
        q1=dict(schedule={**{d: [["10:00", "20:00"]] for d in DAYS[:6]}, "sun": []}, cutoff_minutes=30,
                receiving_contact_name="Amina Saleh", receiving_contact_phone="305-555-0104",
                receiving_instructions="Front office.", curbside_ok=False, curb_location=""),
        q2=dict(dietary_rules=["halal_only"], refused_allergens=["peanuts"], max_meals_per_delivery=60,
                typical_nightly_need=40),
        q3=dict(required_fields=["date_time", "donor_name", "food_description", "quantity_meals", "allergen_info"],
                report_frequency="monthly", report_format="pdf", reports_to="Community committee (fictional)",
                is_501c3=True, ein="00-0000004"),
        verified=False),
    "Hope Family Kitchen": dict(
        lat=25.7610, lng=-80.3480, legal="Hope Family Kitchen Inc. (fictional)", people=("Rebecca Stone", "Victor Pena"),
        q1=dict(schedule=EVERY_DAY([["11:00", "22:00"]]), cutoff_minutes=20,
                receiving_contact_name="Victor Pena", receiving_contact_phone="305-555-0105",
                receiving_instructions="Kitchen entrance off the parking lot.", curbside_ok=True,
                curb_location="Parking lot, kitchen door"),
        q2=dict(dietary_rules=[], refused_allergens=[], max_meals_per_delivery=100,
                typical_nightly_need=70),
        q3=dict(required_fields=["date_time", "donor_name", "food_description", "quantity_meals", "condition"],
                report_frequency="monthly", report_format="csv", reports_to="County family services (fictional)",
                is_501c3=True, ein="00-0000005"),
        verified=True),
    "Sweetwater Youth Center": dict(
        lat=25.7560, lng=-80.3740, legal="Sweetwater Youth Center (fictional)", people=("Daniel Kim", "Nadia Flores"),
        q1=dict(schedule={**{d: [["14:00", "21:00"]] for d in DAYS[:5]}, "sat": [], "sun": []}, cutoff_minutes=30,
                receiving_contact_name="Nadia Flores", receiving_contact_phone="305-555-0106",
                receiving_instructions="Main office, ask at the front desk.", curbside_ok=True,
                curb_location="Front entrance"),
        q2=dict(dietary_rules=[], refused_allergens=["peanuts", "tree_nuts"],
                max_meals_per_delivery=50, typical_nightly_need=35),
        q3=dict(required_fields=["date_time", "donor_name", "food_description", "quantity_meals", "allergen_info"],
                report_frequency="monthly", report_format="csv", reports_to="After-school program board (fictional)",
                is_501c3=True, ein="00-0000006"),
        verified=True),
}

# The street nearest each pin (OpenStreetMap), labelled "Near ..." because these are fictional places
ADDRESSES = {
    "Casa Luna Cocina": "Near SW 107th Ave, Sweetwater, FL 33199",
    "Sunrise Bakehouse": "Near W Flagler St, Miami, FL 33174",
    "Northside Grill": "Near NW 95th Ave, Doral, FL 33172",
    "Coral Pizza Co.": "Near SW 102nd Ave, Miami, FL 33165",
    "Westend Buffet": "Near SW 10th St, Miami, FL 33184",
    "Palm Leaf Thai Kitchen": "Near SW 21st St, Miami, FL 33174",
    "Mango Tree Cafe": "Near SW 2nd St, Sweetwater, FL 33199",
    "Harbor Poke Bar": "Near SW 26th Ter, Miami, FL 33199",
    "Bluebird Diner": "Near NW 10th St, Miami, FL 33172",
    "Green Fork Salads": "Near SW 14th St, Miami, FL 33174",
    "Westchester Community Food Bank": "Westchester, Miami, FL 33165",
    "Safe Harbor Night Shelter": "Near W Flagler St, Miami, FL 33174",
    "Neighbors Community Fridge": "Near East Campus Cir, Miami, FL 33199",
    "Crescent Halal Pantry": "Near SW 32nd Ter, Miami, FL 33165",
    "Hope Family Kitchen": "Near SW 94th Ave, Miami, FL 33174",
    "Sweetwater Youth Center": "Near SW 14th St, Miami, FL 33199",
}

EVENINGS = EVERY_DAY([["17:00", "23:30"]])
# name, home lat/lng, availability, capacity, cooler, bags, max mi, vehicle
VOLUNTEERS = [
    ("Marcus Reed", 25.7580, -80.3720, EVERY_DAY([["17:00", "22:00"]]), 60, True, True, 6, "Gray SUV"),
    ("Aisha Khan", 25.7450, -80.3600, {d: [["12:00", "21:00"]] for d in DAYS[:5]}, 40, False, True, 5, "Blue sedan"),
    ("Diego Morales", 25.7720, -80.3450, {"fri": [["18:00", "23:59"]], "sat": [["18:00", "23:59"]]}, 40, True, False, 5, "Red hatchback"),
    ("Priya Patel", 25.7360, -80.3880, EVERY_DAY([["07:00", "12:00"], ["19:00", "22:00"]]), 80, True, True, 8, "Minivan"),
    ("Sam Carter", 25.7810, -80.3950, EVERY_DAY([["20:00", "23:59"]]), 50, True, True, 8, "White pickup"),
    ("Lena Fischer", 25.7620, -80.3300, {"sat": [["10:00", "22:00"]], "sun": [["10:00", "22:00"]]}, 30, False, True, 4, "Green compact"),
    ("Jamal Brooks", 25.7680, -80.3600, EVENINGS, 45, True, True, 6, "Black SUV"),
    ("Sofia Alvarez", 25.7500, -80.3750, {d: [["18:00", "23:00"]] for d in DAYS[:5]}, 35, False, True, 5, "Silver sedan"),
    ("Kevin Nguyen", 25.7400, -80.3500, EVENINGS, 50, True, True, 7, "Gray minivan"),
    ("Hannah Levi", 25.7750, -80.3800, {d: [["19:00", "23:00"]] for d in ("mon", "wed", "fri", "sat")}, 30, False, False, 4, "White compact"),
    ("Omar Haddad", 25.7550, -80.3400, EVENINGS, 60, True, True, 8, "Blue pickup"),
    ("Grace Kim", 25.7650, -80.3900, {d: [["17:30", "22:30"]] for d in ("tue", "thu", "sat", "sun")}, 35, True, False, 5, "Red sedan"),
    ("Luis Ortega", 25.7850, -80.3550, EVERY_DAY([["21:00", "23:59"]]), 55, True, True, 7, "Gray pickup"),
    ("Emily Chen", 25.7470, -80.3650, {d: [["17:00", "21:00"]] for d in DAYS[:6]}, 40, True, True, 6, "Teal hatchback"),
]


def _email(name: str, domain: str) -> str:
    return f"{name.split()[0].lower()}.{name.split()[-1].lower()}@{domain}.example.com"


def _slug(name: str) -> str:
    return "".join(c for c in name.lower().replace(" ", "-") if c.isalnum() or c == "-").strip("-")


def _user(db: Session, email: str, name: str, role: str, org_id=None, phone="305-555-0199") -> User:
    u = User(email=email.lower(), password_hash="x", name=name, first_name=name.split()[0], role=role,
             organization_id=org_id, phone=phone, is_demo_account=False, created_at=clock.now())
    db.add(u)
    db.flush()
    return u


def seed_accounts(db: Session, admin_email: str, admin_name: str) -> None:
    admin = _user(db, admin_email, admin_name, "admin")
    for i, (name, lat, lng, closing, staffed, totes, fmv, basis, election, usually, people, _menu) in enumerate(RESTAURANTS):
        org = Organization(kind="restaurant", name=name, legal_name=f"{name} LLC (fictional)",
                           address=ADDRESSES[name], lat=lat, lng=lng,
                           is_fictional=True, created_at=clock.now())
        db.add(org)
        db.flush()
        db.add(RestaurantProfile(organization_id=org.id, closing_times={d: closing for d in DAYS},
                                 staffed_until={d: staffed for d in DAYS}, surplus_usually=usually, totes_on_hand=totes,
                                 default_fmv_per_meal=fmv, default_cost_basis_per_meal=basis, basis_election_25pct=election,
                                 pickup_instructions="Back door by the kitchen; ask for the closing cook."))
        domain = _slug(name)
        _user(db, _email(people[0], domain), people[0], "restaurant_manager", org.id, f"305-555-02{i:02d}")
        _user(db, _email(people[1], domain), people[1], "restaurant_staff", org.id, f"305-555-03{i:02d}")
    for name, spec in RECEIVERS.items():
        org = Organization(kind="receiver", name=name, legal_name=spec["legal"],
                           address=ADDRESSES[name], lat=spec["lat"], lng=spec["lng"],
                           is_fictional=True, created_at=clock.now())
        db.add(org)
        db.flush()
        db.add(ReceiverProfile(organization_id=org.id))
        db.flush()
        domain = _slug(name)
        manager = _user(db, _email(spec["people"][0], domain), spec["people"][0], "org_manager", org.id)
        _user(db, _email(spec["people"][1], domain), spec["people"][1], "org_staff", org.id)
        for q, schema in intake.SCHEMAS.items():
            intake.save_answers(db, org.id, q, schema(**spec[q.lower()]), manager)
        if spec["verified"]:
            profile = db.get(ReceiverProfile, org.id)
            profile.ein_verified, profile.ein_verified_by, profile.ein_verified_at = True, admin.id, clock.now()
    for i, (name, lat, lng, avail, cap, cooler, bags, max_mi, vehicle) in enumerate(VOLUNTEERS):
        u = _user(db, _email(name, "driver"), name, "volunteer", phone=f"305-555-04{i:02d}")
        db.add(VolunteerProfile(user_id=u.id, availability=avail, capacity_meals=cap, has_cooler=cooler,
                                has_insulated_bags=bags, max_distance_mi=max_mi, vehicle_description=vehicle,
                                home_lat=lat, home_lng=lng))
    db.commit()


def _at_local(day: date, hhmm: str, minus_min: int) -> datetime:
    h, m = map(int, hhmm.split(":"))
    h += 24 if h < 5 else 0  # a midnight closing belongs to that evening, not the morning before
    local = datetime.combine(day, datetime.min.time()) + timedelta(hours=h, minutes=m - minus_min)
    return clock.local_to_utc(local)


def history(db: Session, days: int, rng: random.Random) -> dict:
    """`days` evenings of rescues: most delivered, some partial, some no-shows, some left to expire."""
    stats = {"posted": 0, "delivered": 0, "partial": 0, "no_show": 0, "left_open": 0, "failed": 0}
    today = clock.to_local(clock.now()).date()
    first = today - timedelta(days=days)
    fc = clock.FakeClock(_at_local(first, "12:00", 0))
    with clock.use(fc):
        for offset in range(days, 0, -1):
            day = today - timedelta(days=offset)
            weekend = day.weekday() >= 4
            picks = rng.sample(RESTAURANTS, rng.randint(3, 6) if weekend else rng.randint(2, 5))
            plan = sorted(((_at_local(day, r[3], rng.randint(20, 50)), r) for r in picks), key=lambda p: p[0])
            for when, r in plan:
                name, menu = r[0], r[11]
                desc, unit, (lo, hi), allergens, tags = rng.choice(menu)
                fc.current = max(fc.now(), when)
                try:
                    rescue = _post(db, name, quantity=rng.randint(lo, hi), unit=unit, description=desc,
                                   allergens=allergens, dietary_tags=tags, deadline_min=rng.choice([60, 75, 90, 120]))
                    stats["posted"] += 1
                    roll = rng.random()
                    trips = _trips(db, rescue, "matched") + _trips(db, rescue, "en_route_pickup")
                    if roll < 0.06 or not trips:
                        # nobody comes: the jobs run past the deadline and the system resolves it (expired)
                        fc.current = max(fc.now(), rescue.pickup_deadline + timedelta(minutes=5))
                        run_jobs(db, reports=False)
                        stats["left_open"] += 1
                    elif roll < 0.12 and trips[0].mode == "volunteer":
                        # first volunteer never shows; after the grace period it re-queues and someone else takes it
                        fc.current = max(fc.now(), trips[0].eta_pickup_at + timedelta(minutes=16))
                        run_jobs(db, reports=False)
                        for t in _trips(db, rescue, "matched") + _trips(db, rescue, "en_route_pickup"):
                            complete(db, fc, t)
                        stats["no_show"] += 1
                    elif roll < 0.22:
                        receipts = {s.organization.name: ("partially_accepted", max(1, s.allocated_meals // 2),
                                                          rng.choice(["packaging", "quantity", "temperature"]),
                                                          rng.choice(["two pans arrived uncovered", "more than we can store tonight",
                                                                      "one tray was not covered"]))
                                    for t in trips for s in t.stops}
                        for t in trips:
                            complete(db, fc, t, receipts)
                        stats["partial"] += 1
                    else:
                        for t in trips:
                            complete(db, fc, t)
                        stats["delivered"] += 1
                    db.commit()
                except Exception as e:  # one odd rescue must not sink the whole dataset
                    db.rollback()
                    stats["failed"] += 1
                    print(f"  skipped a rescue from {name} on {day}: {type(e).__name__}: {e}", file=sys.stderr)
    return stats


def _lit(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return repr(v)
    s = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
    return "'" + s.replace("'", "''") + "'"


def dump_sql(out: Path, part_kb: int) -> tuple[dict, list[Path]]:
    """Write the SQL in numbered parts of about `part_kb` KB (the Supabase SQL editor caps query size).
    Part 1 truncates every table; run the parts in order."""
    tables = [t for t in Base.metadata.sorted_tables if t.name not in SKIP_TABLES]
    counts = {}
    stmts = ["TRUNCATE TABLE " + ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables) + " RESTART IDENTITY CASCADE;"]
    with engine.connect() as conn:
        for t in tables:
            rows = conn.execute(select(t)).all()
            counts[t.name] = len(rows)
            cols = ", ".join(f'"{c.name}"' for c in t.columns)
            for i in range(0, len(rows), 50):
                values = ",\n  ".join("(" + ", ".join(_lit(v) for v in row) + ")" for row in rows[i:i + 50])
                stmts.append(f'INSERT INTO "{t.name}" ({cols}) VALUES\n  {values};')
    for t in Base.metadata.sorted_tables:
        pk = list(t.primary_key.columns)
        if len(pk) == 1 and pk[0].name == "id" and pk[0].autoincrement in (True, "auto") and t.name != "job_locks":
            stmts.append(f"SELECT setval(pg_get_serial_sequence('\"{t.name}\"', 'id'), "
                         f"COALESCE((SELECT MAX(id) FROM \"{t.name}\"), 1), (SELECT MAX(id) IS NOT NULL FROM \"{t.name}\"));")
    parts: list[list[str]] = [[]]
    size = 0
    for s in stmts:
        if parts[-1] and size + len(s) > part_kb * 1024:
            parts.append([])
            size = 0
        parts[-1].append(s)
        size += len(s) + 1
    for old in out.parent.glob(f"{out.stem}*{out.suffix}"):
        old.unlink()
    paths = []
    for n, body in enumerate(parts, 1):
        p = out.with_name(f"{out.stem}_{n}_of_{len(parts)}{out.suffix}")
        head = [f"-- FoodFlow demo data (FICTIONAL), part {n} of {len(parts)}: run the parts in order.",
                "-- Generated by backend/scripts/export_demo_sql.py." + (" Part 1 empties every table first." if n == 1 else "")]
        p.write_text("\n".join(head + ["BEGIN;"] + body + ["COMMIT;"]) + "\n", encoding="utf-8")
        paths.append(p)
    return counts, paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Write fictional FoodFlow demo data as Postgres SQL.")
    parser.add_argument("admin_email")
    parser.add_argument("admin_name")
    parser.add_argument("--days", type=int, default=14, help="evenings of rescue history (default 14)")
    parser.add_argument("--part-kb", type=int, default=200, help="size of each SQL part (default 200 KB)")
    parser.add_argument("--seed", type=int, default=7, help="random seed, for a repeatable dataset")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "demo_data.sql"))
    args = parser.parse_args()
    password = os.environ.get("DEMO_SQL_PASSWORD")
    if password is None:
        password = getpass.getpass("Password for every account (admin and demo users): ")
        if getpass.getpass("Repeat password: ") != password:
            raise SystemExit("The passwords do not match.")
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise SystemExit(f"The password must be {PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters.")

    create_schema(engine)
    with SessionLocal() as db:
        print("Creating accounts, restaurants, receivers and volunteers...")
        seed_accounts(db, args.admin_email.strip(), args.admin_name.strip())
        print(f"Running {args.days} evenings of rescues through the real services (takes a minute)...")
        stats = history(db, args.days, random.Random(args.seed))
        pw_hash = hash_password(password)
        for u in db.query(User).all():
            u.password_hash = pw_hash
        db.commit()
    counts, paths = dump_sql(Path(args.out), args.part_kb)
    print(f"\nRescues: {stats}")
    print("Rows: " + ", ".join(f"{k} {v}" for k, v in counts.items() if v))
    print("\nWrote, to run in this order in the Supabase SQL editor:")
    for p in paths:
        print(f"  {p} ({p.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
