"""Demo seed. EVERY NAME, ADDRESS, EIN AND ACCOUNT HERE IS FICTIONAL.

Demo sign-in (only while DEMO_MODE=true): POST /auth/login with any email below and
the password DEMO_PASSWORD.

  restaurant_staff    staff@casa-demo.example.com (Casa Demo Cocina)
  restaurant_manager  manager@casa-demo.example.com (Casa Demo Cocina)
  volunteer           marcus@volunteer-demo.example.com (Marcus)
  org_staff           staff@shelter-demo.example.com (Demo Night Shelter)
  org_manager         manager@shelter-demo.example.com (Demo Night Shelter)
  admin               admin@foodflow-demo.example.com

  python -m app.seed      (from backend/) resets the database to this state

Scenario history (completed rescue, no-show, partial acceptance, late-night
simulated AV delivery, missed AV window with volunteer fallback) is created by
running the real services under a fake clock: see app/demo_scenarios.py.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app import clock, intake
from app.auth import hash_password
from app.db import Base, SessionLocal, create_schema, drop_schema, engine
from app.models import Organization, ReceiverProfile, RestaurantProfile, User, VolunteerProfile

DEMO_PASSWORD = "demo1234"  # every demo account; published, so it works only while DEMO_MODE is on
DAYS = intake.WEEKDAYS

# name, lat, lng, staffed_until (every day), closing, totes, fmv/meal, basis/meal, election, surplus_usually
RESTAURANTS = [
    ("Casa Demo Cocina", 25.7630, -80.3690, "23:30", "22:00", 6, 9.0, 3.0, False, "after dinner service, 9:30 to 10 PM"),
    ("Demo Bakery Uno", 25.7700, -80.3450, "21:00", "20:00", 2, 4.0, None, True, "at closing, 8 PM"),
    ("Demo Grill Norte", 25.7930, -80.3500, "01:00", "00:00", 4, 11.0, 4.0, False, "late night, 11 PM to midnight"),
    ("Demo Pizza Sur", 25.7350, -80.3600, "22:30", "22:00", 0, 3.5, 1.2, False, "at closing"),
    ("Demo Buffet Oeste", 25.7580, -80.4000, "00:30", "23:00", 8, 7.0, 2.5, False, "after the 10 PM buffet close"),
]

EVERY_DAY = lambda windows: {d: windows for d in DAYS}  # noqa: E731

ORGS = {
    "Demo Food Bank": dict(
        lat=25.7480, lng=-80.3500, legal="Demo Food Bank Inc. (fictional)",
        q1=dict(schedule={**{d: [["08:00", "17:00"]] for d in DAYS[:5]}, "sat": [["09:00", "13:00"]], "sun": []},
                cutoff_minutes=30, receiving_contact_name="Dock lead (fictional)", receiving_contact_phone="305-555-0101",
                receiving_instructions="Loading dock at the back, ring the bell.", curbside_ok=True,
                curb_location="Loading dock driveway"),
        q2=dict(dietary_rules=[], refused_allergens=[],
                max_meals_per_delivery=150, typical_nightly_need=100),
        q3=dict(required_fields=["date_time", "donor_name", "donor_address", "food_description",
                                 "quantity_meals", "weight_lbs"],
                report_frequency="monthly", report_format="csv", reports_to="Partner food bank network (fictional)",
                is_501c3=True, ein="00-0000001"),
        verified=True),
    "Demo Night Shelter": dict(
        lat=25.7700, lng=-80.3550, legal="Demo Night Shelter Corp. (fictional)",
        q1=dict(schedule=EVERY_DAY([["16:00", "24:00"]]), cutoff_minutes=15,
                receiving_contact_name="Night supervisor (fictional)", receiving_contact_phone="305-555-0102",
                receiving_instructions="Side door on the east wall, doorbell.", curbside_ok=True,
                curb_location="East side door, loading zone"),
        q2=dict(dietary_rules=[], refused_allergens=[], max_meals_per_delivery=80, typical_nightly_need=60),
        q3=dict(required_fields=["date_time", "donor_name", "food_description", "quantity_meals",
                                 "condition", "received_by_name"],
                report_frequency="per_delivery", report_format="pdf", reports_to="City homeless services program (fictional)",
                is_501c3=True, ein="00-0000002"),
        verified=True),
    "Demo Community Fridge": dict(
        lat=25.7545, lng=-80.3790, legal="Demo Community Fridge Collective (fictional)",
        q1=dict(schedule=EVERY_DAY([["00:00", "24:00"]]), cutoff_minutes=0,
                receiving_contact_name="Fridge steward on call (fictional)", receiving_contact_phone="305-555-0103",
                receiving_instructions="Fridge is outside by the front gate; label with date.", curbside_ok=True,
                curb_location="Front gate"),
        q2=dict(dietary_rules=[], refused_allergens=[], max_meals_per_delivery=40,
                typical_nightly_need=30),
        q3=dict(required_fields=["date_time", "food_description", "quantity_meals"], report_frequency="weekly",
                report_format="csv", reports_to="", is_501c3=False, ein=None),
        verified=False),
    "Demo Halal Pantry": dict(
        lat=25.7400, lng=-80.3350, legal="Demo Halal Pantry (fictional)",
        q1=dict(schedule={**{d: [["10:00", "20:00"]] for d in DAYS[:6]}, "sun": []}, cutoff_minutes=30,
                receiving_contact_name="Pantry coordinator (fictional)", receiving_contact_phone="305-555-0104",
                receiving_instructions="Front office.", curbside_ok=False, curb_location=""),
        q2=dict(dietary_rules=["halal_only"], refused_allergens=["peanuts"], max_meals_per_delivery=60,
                typical_nightly_need=40),
        q3=dict(required_fields=["date_time", "donor_name", "food_description", "quantity_meals", "allergen_info"],
                report_frequency="monthly", report_format="pdf", reports_to="Mosque community committee (fictional)",
                is_501c3=True, ein="00-0000004"),
        verified=False),
}

# name, email, home lat/lng, availability, capacity, cooler, bags, max mi, vehicle
VOLUNTEERS = [
    ("Marcus", "marcus@volunteer-demo.example.com", 25.7580, -80.3720, EVERY_DAY([["17:00", "22:00"]]), 60, True, True, 6, "Gray SUV"),
    ("Aisha", "aisha@volunteer-demo.example.com", 25.7450, -80.3600, {d: [["12:00", "21:00"]] for d in DAYS[:5]}, 40, False, True, 5, "Blue sedan"),
    ("Diego", "diego@volunteer-demo.example.com", 25.7720, -80.3450, {"fri": [["18:00", "23:00"]], "sat": [["18:00", "23:00"]]}, 40, True, False, 5, "Red hatchback"),
    ("Priya", "priya@volunteer-demo.example.com", 25.7360, -80.3880, EVERY_DAY([["07:00", "12:00"]]), 80, True, True, 8, "Minivan"),
    ("Sam", "sam@volunteer-demo.example.com", 25.7810, -80.3950, EVERY_DAY([["20:00", "23:30"]]), 50, True, True, 8, "White pickup"),
    ("Lena", "lena@volunteer-demo.example.com", 25.7620, -80.3300, {"sat": [["10:00", "18:00"]], "sun": [["10:00", "18:00"]]}, 30, False, True, 4, "Green compact"),
]


@lru_cache(maxsize=1)
def _demo_password_hash() -> str:
    """Hashed once per process and shared: the demo password is public, so a per-account salt protects nothing."""
    return hash_password(DEMO_PASSWORD)


def _user(db: Session, email: str, name: str, role: str, org_id=None, phone="305-555-0199") -> User:
    u = User(email=email, password_hash=_demo_password_hash(), name=name, first_name=name.split()[0], role=role,
             organization_id=org_id, phone=phone, is_demo_account=True, created_at=clock.now())
    db.add(u)
    db.flush()
    return u


def seed_accounts(db: Session) -> Dict[str, int]:
    ids: Dict[str, int] = {}
    admin = _user(db, "admin@foodflow-demo.example.com", "Demo Admin", "admin")
    ids["admin"] = admin.id
    for i, (name, lat, lng, staffed, closing, totes, fmv, basis, election, usually) in enumerate(RESTAURANTS):
        org = Organization(kind="restaurant", name=name, legal_name=f"{name} LLC (fictional)",
                           address="Demo location near FIU (fictional business)", lat=lat, lng=lng, is_fictional=True,
                           created_at=clock.now())
        db.add(org)
        db.flush()
        db.add(RestaurantProfile(organization_id=org.id, closing_times={d: closing for d in DAYS},
                                 staffed_until={d: staffed for d in DAYS}, surplus_usually=usually, totes_on_hand=totes,
                                 default_fmv_per_meal=fmv, default_cost_basis_per_meal=basis, basis_election_25pct=election,
                                 pickup_instructions="Back door by the kitchen; ask for the closing cook (fictional)."))
        ids[name] = org.id
        slug = name.lower().replace(" ", "-")
        if i == 0:
            ids["restaurant_staff"] = _user(db, "staff@casa-demo.example.com", "Rosa Demo", "restaurant_staff", org.id).id
            ids["restaurant_manager"] = _user(db, "manager@casa-demo.example.com", "Luis Demo", "restaurant_manager", org.id).id
        else:
            _user(db, f"manager@{slug}.example.com", f"{name} Manager", "restaurant_manager", org.id)
    for name, spec in ORGS.items():
        org = Organization(kind="receiver", name=name, legal_name=spec["legal"], address="Demo location near FIU (fictional)",
                           lat=spec["lat"], lng=spec["lng"], is_fictional=True, created_at=clock.now())
        db.add(org)
        db.flush()
        db.add(ReceiverProfile(organization_id=org.id))
        db.flush()
        slug = name.lower().replace(" ", "-")
        if name == "Demo Night Shelter":
            manager = _user(db, "manager@shelter-demo.example.com", "Grace Demo", "org_manager", org.id)
            ids["org_staff"] = _user(db, "staff@shelter-demo.example.com", "Tomas Demo", "org_staff", org.id).id
        else:
            manager = _user(db, f"manager@{slug}.example.com", f"{name} Manager", "org_manager", org.id)
        ids["org_manager" if name == "Demo Night Shelter" else f"{name} manager"] = manager.id
        for q, schema in intake.SCHEMAS.items():
            intake.save_answers(db, org.id, q, schema(**spec[q.lower()]), manager)
        if spec["verified"]:
            profile = db.get(ReceiverProfile, org.id)
            profile.ein_verified, profile.ein_verified_by, profile.ein_verified_at = True, admin.id, clock.now()
        ids[name] = org.id
    for name, email, lat, lng, avail, cap, cooler, bags, max_mi, vehicle in VOLUNTEERS:
        u = _user(db, email, name, "volunteer", phone="305-555-0150")
        db.add(VolunteerProfile(user_id=u.id, availability=avail, capacity_meals=cap, has_cooler=cooler,
                                has_insulated_bags=bags, max_distance_mi=max_mi, vehicle_description=vehicle,
                                home_lat=lat, home_lng=lng))
        ids[name] = u.id
        if name == "Marcus":
            ids["volunteer"] = u.id
    db.flush()
    return ids


def seed(db: Session, with_scenarios: bool = True) -> Dict[str, int]:
    ids = seed_accounts(db)
    db.commit()
    if with_scenarios:
        from app.demo_scenarios import run_all

        run_all(db, ids)
    return ids


def reset_database(with_scenarios: bool = True) -> None:
    drop_schema(engine)
    create_schema(engine)
    with SessionLocal() as db:
        seed(db, with_scenarios)


def schema_is_current() -> bool:
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in tables:
            return False
        have = {c["name"] for c in insp.get_columns(table.name)}
        if not {c.name for c in table.columns} <= have:
            return False
    return True


def seed_if_empty() -> None:
    if not schema_is_current():
        # Dropping every table is only acceptable for the local demo database. Anywhere else
        # (e.g. Supabase with DEMO_MODE left on) an outdated schema must go through migrations.
        if engine.dialect.name != "sqlite" and inspect(engine).get_table_names():
            raise RuntimeError("DEMO_MODE found an outdated schema on a non-SQLite database and will not drop it. "
                               "Run `alembic upgrade head`, or set DEMO_MODE=false.")
        reset_database()
        return
    create_schema(engine)
    with SessionLocal() as db:
        if db.query(User).first() is None:
            seed(db)


if __name__ == "__main__":
    reset_database()
    print("Database reset to the fictional demo seed.")

