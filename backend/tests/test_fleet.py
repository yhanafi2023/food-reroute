"""Section 6: mixed fleet with SIMULATED autonomous vehicles and robots (no Waymo API)."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import clock, dispatch
from app.db import SessionLocal
from app.fleet import geofence
from app.fleet.base import Cargo
from app.fleet.simulated import SimulatedSidewalkRobotProvider, SimulatedWaymoProvider
from app.jobs import run_jobs
from app.main import app
from app.models import AuditEvent, Organization, Rescue, Trip, User, VolunteerProfile
from app.seed import reset_database
from tests.helpers import signin

FRI_2340 = clock.local_to_utc(datetime(2026, 9, 25, 23, 40))
GRILL = "manager@demo-grill-norte.example.com"
FRIDGE = "manager@demo-community-fridge.example.com"


@pytest.fixture()
def client(fake_clock):
    reset_database(with_scenarios=False)
    with TestClient(app) as c:
        yield c


def post(client, email, **kw):
    b = {"quantity": 3, "unit": "bag", "attested": True,
         "pickup_deadline": (clock.now() + timedelta(minutes=90)).isoformat() + "Z", **kw}
    r = client.post("/rescues", json=b, headers=signin(client, email))
    assert r.status_code == 200, r.text
    return r.json()["rescue"]


def jobs():
    with SessionLocal() as db:
        return run_jobs(db)


def test_zone_is_labeled_illustrative_and_providers_say_simulated(client):
    z = client.get("/fleet/availability", headers=signin(client, "admin@foodflow-demo.example.com")).json()
    assert z["zone"]["label"] == "illustrative demo zone" and "NOT an official Waymo" in z["zone"]["note"]
    assert all(p["simulated"] for p in z["providers"] if p["mode"] != "volunteer")
    assert geofence.contains(25.7630, -80.3690) and not geofence.contains(25.7784, -80.1409)  # Miami Beach is outside


def test_late_night_simulated_av_delivery_full_curbside_handoff(client, fake_clock):
    fake_clock.current = FRI_2340
    r = post(client, GRILL)
    t = r["trips"][0]
    assert t["mode"] == "waymo_sim" and t["simulated"] and t["carrier"]["simulated"]
    assert "Simulated Waymo selected" in t["mode_reason"] and "illustrative service zone" in t["mode_reason"]
    assert "no driver can take it" in t["mode_reason"] and t["handoff_state"] == "vehicle_arriving"
    fake_clock.current = datetime.fromisoformat(t["eta_pickup"].rstrip("Z")) + timedelta(seconds=1)  # API times are whole seconds
    assert jobs()["vehicle_moves"] == 1
    grill = signin(client, GRILL)
    assert client.get(f"/trips/{t['id']}", headers=grill).json()["handoff_state"] == "at_pickup_curb"
    assert client.post(f"/trips/{t['id']}/curb/unlock", json={"code": "0000" if r["pickup_code"] != "0000" else "1111"}, headers=grill).status_code == 400
    assert client.post(f"/trips/{t['id']}/curb/unlock", json={"code": r["pickup_code"]}, headers=grill).status_code == 200
    loaded = client.post(f"/trips/{t['id']}/curb/loaded", json={"item_count": 12}, headers=grill).json()
    assert loaded["handoff_state"] == "in_transit" and loaded["status"] == "en_route_dropoff"
    fake_clock.current = datetime.fromisoformat(loaded["stops"][0]["eta"].rstrip("Z")) + timedelta(seconds=1)
    jobs()
    fridge = signin(client, FRIDGE)
    stop = client.get("/orgs/me/deliveries", headers=fridge).json()["incoming"][0]["stop"]
    assert client.post(f"/trips/{t['id']}/curb/unloaded", headers=fridge).status_code == 409  # unlock first
    assert client.post(f"/trips/{t['id']}/curb/unlock", json={"code": stop["dropoff_code"]}, headers=fridge).status_code == 200
    assert client.post(f"/trips/{t['id']}/curb/unloaded", headers=fridge).json()["handoff_state"] == "unloaded"
    rec = client.post(f"/stops/{stop['id']}/receipt", json={"condition": "accepted"}, headers=fridge)
    assert rec.status_code == 200 and rec.json()["status"] == "received"
    final = client.get(f"/trips/{t['id']}", headers=grill).json()
    assert final["status"] == "received" and final["handoff_state"] == "received"
    with SessionLocal() as db:
        states = [e.to_state for e in db.query(AuditEvent).filter(AuditEvent.trip_id == t["id"], AuditEvent.action.like("vehicle_%"),
                                                                  AuditEvent.to_state.isnot(None)).order_by(AuditEvent.id)]
        assert states == ["at_pickup_curb", "loading", "loaded", "in_transit", "at_dropoff_curb", "unloaded", "received"]
        assert all(e.details.get("simulated") for e in db.query(AuditEvent).filter(AuditEvent.trip_id == t["id"], AuditEvent.action.like("vehicle_%")))


def test_missed_load_window_falls_back_to_a_volunteer(client, fake_clock):
    fake_clock.current = FRI_2340
    r = post(client, GRILL)
    t = r["trips"][0]
    assert t["mode"] == "waymo_sim"
    fake_clock.current = datetime.fromisoformat(t["eta_pickup"].rstrip("Z")) + timedelta(seconds=1)  # API times are whole seconds
    jobs()  # vehicle at the curb, load timer starts
    with SessionLocal() as db:  # a late volunteer comes online meanwhile
        sam = db.query(User).filter_by(first_name="Sam").one()
        db.get(VolunteerProfile, sam.id).availability = {d: [["00:00", "24:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
        db.commit()
    fake_clock.advance(minutes=6)  # nobody loaded within 5 minutes
    counts = jobs()
    assert counts["av_load_missed"] == 1
    x = client.get(f"/rescues/{r['id']}", headers=signin(client, GRILL)).json()
    assert x["trips"][0]["status"] == "reassigned"
    fallback = [tr for tr in x["trips"] if tr["status"] == "matched"]
    assert fallback and fallback[0]["mode"] == "volunteer" and fallback[0]["carrier"]["first_name"] == "Sam"
    with SessionLocal() as db:
        assert db.get(Rescue, r["id"]).allowed_modes == ["volunteer"]
        assert db.query(AuditEvent).filter_by(rescue_id=r["id"], action="av_load_window_missed").count() == 1


def test_av_never_chosen_when_restaurant_unstaffed_or_outside_zone(client, fake_clock):
    fake_clock.current = FRI_2340
    r = post(client, "staff@casa-demo.example.com")  # Casa is staffed until 11:30 PM
    assert all(t["mode"] != "waymo_sim" for t in r["trips"])
    assert r["status"] == "posted"
    client.post("/auth/register-organization", json={"kind": "restaurant", "organization_name": "South Kitchen (test)", "address": "300 Test St, Miami FL",
               "lat": 25.700, "lng": -80.370, "manager_name": "Kim Test", "manager_email": "kim@south.example.com",
               "manager_password": "kim-password"})
    with SessionLocal() as db:
        org = db.query(Organization).filter_by(name="South Kitchen (test)").one()
        org.restaurant_profile.staffed_until = {d: "02:00" for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
        org.restaurant_profile.totes_on_hand = 10
        db.commit()
    h = signin(client, "kim@south.example.com", "kim-password")
    b = {"quantity": 3, "unit": "bag", "attested": True,
         "pickup_deadline": (clock.now() + timedelta(minutes=90)).isoformat() + "Z"}
    r2 = client.post("/rescues", json=b, headers=h).json()["rescue"]
    assert all(t["mode"] != "waymo_sim" for t in r2["trips"])


def test_no_av_dropoff_where_curbside_is_false(client):
    with SessionLocal() as db:
        halal = db.query(Organization).filter_by(name="Demo Halal Pantry").one()
        rescue_org = db.query(Organization).filter_by(name="Casa Demo Cocina").one()
        rescue = Rescue(restaurant_org_id=rescue_org.id, quantity=1, unit="bag", meals_per_unit=4, est_meals=4,
                        safe_until=clock.now() + timedelta(hours=5),
                        pickup_deadline=clock.now() + timedelta(hours=2), pickup_code="1234", attested_by=1,
                        attested_at=clock.now(), dietary_tags=["halal"], allergens_declared=True)
        db.add(rescue)
        db.flush()
        from app import eligibility
        reasons, _ = eligibility.check(db, halal.receiver_profile, rescue, clock.now(), clock.now() + timedelta(minutes=20), "waymo_sim")
        assert any(r["code"] == "curbside" for r in reasons)
        reasons_v, _ = eligibility.check(db, halal.receiver_profile, rescue, clock.now(), clock.now() + timedelta(minutes=20), "volunteer")
        assert not any(r["code"] == "curbside" for r in reasons_v)
        db.rollback()


def test_split_allocation_becomes_point_to_point_av_trips(client):
    with SessionLocal() as db:
        casa = db.query(User).filter_by(email="staff@casa-demo.example.com").one()
        from app import posting
        res = posting.create_post(db, casa, posting.QuickPost(quantity=10, unit="box", attested=True,
                                                              pickup_deadline=clock.now() + timedelta(minutes=90)))
        rescue = res["rescue"]
        rescue.allowed_modes = ["waymo_sim"]
        out = dispatch.run_matching(db, rescue)
        db.commit()
        assert out["matched"]
        trips = db.query(Trip).filter_by(rescue_id=rescue.id).all()
        assert len(trips) >= 2 and all(len(t.stops) == 1 and t.mode == "waymo_sim" and t.simulated for t in trips)
        assert sum(t.stops[0].allocated_meals for t in trips) == 80
        assert all(t.stops[0].allocated_meals <= 60 for t in trips)


def test_robot_constraints(client):
    with SessionLocal() as db:
        robot = SimulatedSidewalkRobotProvider(db)
        near = robot.quote((25.7630, -80.3690), (25.7545, -80.3790), Cargo(12), clock.now())
        assert near.feasible and near.simulated
        far = robot.quote((25.7630, -80.3690), (25.7400, -80.3350), Cargo(12), clock.now())
        assert not far.feasible and "range" in far.reason
        big = robot.quote((25.7630, -80.3690), (25.7545, -80.3790), Cargo(30), clock.now())
        assert not big.feasible and "capacity" in big.reason
        av = SimulatedWaymoProvider(db).quote((25.7630, -80.3690), (25.7784, -80.1409), Cargo(12), clock.now())
        assert not av.feasible and "outside the illustrative service zone" in av.reason


def test_mode_selection_is_deterministic(client, fake_clock):
    fake_clock.current = FRI_2340
    a = post(client, GRILL)["trips"][0]
    reset_database(with_scenarios=False)
    b = post(client, GRILL)["trips"][0]
    assert (a["mode"], a["eta_pickup"], a["mode_reason"]) == (b["mode"], b["eta_pickup"], b["mode_reason"])
