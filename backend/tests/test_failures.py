"""Section 7: what happens when things go wrong (fake clock, no sleeping)."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import clock
from app.db import SessionLocal
from app.jobs import run_jobs
from app.main import app
from app.models import AuditEvent, Notification, Rescue, Trip, User
from app.seed import ORGS, reset_database
from tests.helpers import EMAILS, signin


@pytest.fixture()
def client(fake_clock):
    reset_database(with_scenarios=False)
    with TestClient(app) as c:
        yield c


def post(client, h, **kw):
    b = {"quantity": 2, "unit": "tray", "category": "hot", "attested": True,
         "pickup_deadline": (clock.now() + timedelta(minutes=110)).isoformat() + "Z", **kw}
    r = client.post("/rescues", json=b, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["rescue"]


def jobs():
    with SessionLocal() as db:
        return run_jobs(db)


def events_for(email):
    with SessionLocal() as db:
        u = db.query(User).filter_by(email=email).one()
        return [n.event for n in db.query(Notification).filter_by(user_id=u.id)]


def test_volunteer_no_show_requeues_and_notifies_restaurant(client, fake_clock):
    h = signin(client, EMAILS["restaurant_staff"])
    r = post(client, h)
    first = r["trips"][0]
    assert first["carrier"]["first_name"] == "Marcus"
    fake_clock.advance(minutes=10)
    assert jobs()["no_shows"] == 0  # still inside the grace period
    fake_clock.advance(minutes=20)
    assert jobs()["no_shows"] == 1
    after = client.get(f"/rescues/{r['id']}", headers=h).json()
    old = next(t for t in after["trips"] if t["id"] == first["id"])
    assert old["status"] == "reassigned"
    new = [t for t in after["trips"] if t["status"] == "matched"]
    assert new and new[0]["carrier"]["first_name"] != "Marcus" and after["requeue_count"] == 1
    assert "reassigned" in events_for(EMAILS["restaurant_staff"])
    assert "reassigned" in events_for(EMAILS["volunteer"])


def test_food_past_safe_until_expires_and_everyone_is_told(client, fake_clock):
    h = signin(client, EMAILS["restaurant_staff"])
    r = post(client, h, prepared_at=(clock.now() - timedelta(minutes=95)).isoformat() + "Z")  # safe 25 more minutes
    assert r["trips"] and r["trips"][0]["carrier"]["first_name"] == "Marcus"
    fake_clock.advance(minutes=26)  # past safe_until and past the no-show grace: expiry wins, no re-queue
    assert jobs()["expired"] == 1
    x = client.get(f"/rescues/{r['id']}", headers=h).json()
    assert x["status"] == "expired" and x["trips"] and all(t["status"] == "expired" for t in x["trips"])
    assert x["requeue_count"] == 0
    for who in ("restaurant_staff", "volunteer", "org_staff"):
        assert "expired" in events_for(EMAILS[who]), who
    with SessionLocal() as db:
        assert db.query(AuditEvent).filter_by(rescue_id=r["id"], action="rescue_expired").count() == 1


def _to_dropoff(client, category="cold"):
    rest, vol = signin(client, EMAILS["restaurant_staff"]), signin(client, EMAILS["volunteer"])
    r = post(client, rest, category=category, unit="bag", quantity=3)
    trip = r["trips"][0]
    client.post(f"/trips/{trip['id']}/accept", headers=vol)
    client.post(f"/trips/{trip['id']}/pickup", json={"code": r["pickup_code"], "picked_up_meals": 12}, headers=vol)
    return r, trip, rest, vol


def test_org_closed_on_arrival_reroutes_to_next_eligible_org(client):
    r, trip, rest, vol = _to_dropoff(client)
    first_stop = trip["stops"][0]
    res = client.post(f"/stops/{first_stop['id']}/report-closed", json={"reason": "closed"}, headers=vol)
    assert res.status_code == 200 and res.json()["rerouted_to"] is not None
    new_org = res.json()["rerouted_to"]["organization"]["name"]
    assert new_org != first_stop["organization"]["name"]
    assert "rerouted" in events_for(EMAILS["volunteer"])


def test_schedule_change_after_pickup_reroutes_automatically(client):
    r, trip, rest, vol = _to_dropoff(client)
    first = trip["stops"][0]["organization"]["name"]
    mgr_email = EMAILS["org_manager"] if first == "Demo Night Shelter" else "manager@demo-community-fridge.example.com"
    spec = ORGS[first]["q1"]
    closed = {**spec, "schedule": {d: [] for d in spec["schedule"]}}
    assert client.put("/orgs/me/intake/Q1", json=closed, headers=signin(client, mgr_email)).status_code == 200
    assert jobs()["reroutes"] == 1
    t = client.get(f"/trips/{trip['id']}", headers=vol).json()
    assert [s["status"] for s in t["stops"]][:1] == ["rerouted"] and t["stops"][-1]["status"] == "pending"


def test_org_refuses_before_arrival(client):
    r, trip, rest, vol = _to_dropoff(client)
    stop = trip["stops"][0]
    org_email = EMAILS["org_staff"] if stop["organization"]["name"] == "Demo Night Shelter" else "manager@demo-community-fridge.example.com"
    res = client.post(f"/stops/{stop['id']}/refuse", json={"reason": "full"}, headers=signin(client, org_email))
    assert res.status_code == 200 and res.json()["rerouted"] is True


def test_restaurant_cancel_after_match_closes_trip_and_notifies_carrier(client):
    h = signin(client, EMAILS["restaurant_staff"])
    r = post(client, h)
    client.post(f"/rescues/{r['id']}/cancel", json={"reason": "fire alarm"}, headers=h)
    with SessionLocal() as db:
        assert db.get(Trip, r["trips"][0]["id"]).status == "cancelled"
    assert "cancelled" in events_for(EMAILS["volunteer"])


def test_routing_and_allocation_services_down_fall_back_with_estimated_flag(client, monkeypatch):
    import app.clients as clients
    monkeypatch.setattr(clients, "ROUTING_SERVICE_URL", "http://127.0.0.1:9")    # nothing listens here
    monkeypatch.setattr(clients, "ALLOCATION_SERVICE_URL", "http://127.0.0.1:9")
    h = signin(client, EMAILS["restaurant_staff"])
    r = post(client, h)
    assert r["status"] == "matched"
    t = r["trips"][0]
    assert t["estimated"] is True
    with SessionLocal() as db:
        ev = db.query(AuditEvent).filter_by(rescue_id=r["id"], action="matched").one()
        assert ev.details["estimated"] is True and ev.details["allocation_source"] == "fallback"
