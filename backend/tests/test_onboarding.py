"""Section 2: the three required intake questions, completeness, receiving hours, profiles."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import intake
from app.db import SessionLocal
from app.main import app
from app.models import IntakeAnswer, ReceiverProfile
from app.seed import ORGS, reset_database
from tests.helpers import EMAILS, signin


@pytest.fixture()
def client(fake_clock):
    reset_database(with_scenarios=False)
    with TestClient(app) as c:
        yield c


def _new_org(client):
    r = client.post("/auth/register-organization", json={
        "kind": "receiver", "organization_name": "Test Pantry", "address": "200 Test St, Miami FL", "lat": 25.75, "lng": -80.36,
        "manager_name": "Pat Test", "manager_email": "pat@pantry.example.com", "manager_password": "pat-password"})
    assert r.status_code == 200, r.text
    return signin(client, "pat@pantry.example.com", "pat-password")


def test_org_is_incomplete_until_all_three_answered(client):
    mgr = _new_org(client)
    me = client.get("/orgs/me/profile", headers=mgr).json()
    oid = me["organization"]["id"]
    comp = client.get(f"/orgs/{oid}/profile-completeness", headers=mgr).json()
    assert comp == {**comp, "complete": False, "missing": ["Q1", "Q2", "Q3"], "receives_deliveries": False}
    spec = ORGS["Demo Night Shelter"]
    for i, q in enumerate(("Q1", "Q2", "Q3")):
        r = client.put(f"/orgs/me/intake/{q}", json=spec[q.lower()], headers=mgr)
        assert r.status_code == 200, r.text
        assert r.json()["completeness"]["complete"] is (i == 2)
    comp = client.get(f"/orgs/{oid}/profile-completeness", headers=mgr).json()
    assert comp["complete"] and comp["questions"]["Q2"]["source"] == "self_reported_by_org"
    assert comp["questions"]["Q1"]["answered_by"] is not None
    other = signin(client, EMAILS["org_manager"])
    assert client.get(f"/orgs/{oid}/profile-completeness", headers=other).status_code == 404


def test_answer_validation(client):
    mgr = _new_org(client)
    q1 = dict(ORGS["Demo Night Shelter"]["q1"])
    bad = {**q1, "schedule": {k: v for k, v in q1["schedule"].items() if k != "sun"}}
    assert client.put("/orgs/me/intake/Q1", json=bad, headers=mgr).status_code == 422
    assert client.put("/orgs/me/intake/Q1", json={**q1, "schedule": {**q1["schedule"], "mon": [["22:00", "02:00"]]}}, headers=mgr).status_code == 422
    assert client.put("/orgs/me/intake/Q1", json={**q1, "curbside_ok": True, "curb_location": ""}, headers=mgr).status_code == 422
    q2 = dict(ORGS["Demo Night Shelter"]["q2"])
    assert client.put("/orgs/me/intake/Q2", json={**q2, "max_meals_per_delivery": 0}, headers=mgr).status_code == 422
    assert client.put("/orgs/me/intake/Q2", json={**q2, "dietary_rules": ["only_pizza"]}, headers=mgr).status_code == 422
    q3 = dict(ORGS["Demo Night Shelter"]["q3"])
    assert client.put("/orgs/me/intake/Q3", json={**q3, "ein": None}, headers=mgr).status_code == 422
    assert client.put("/orgs/me/intake/Q3", json={**q3, "required_fields": []}, headers=mgr).status_code == 422
    staff = signin(client, EMAILS["org_staff"])
    assert client.put("/orgs/me/intake/Q1", json=q1, headers=staff).status_code == 403  # managers only


def test_answers_are_kept_with_provenance_and_90_day_confirmation(client, fake_clock):
    mgr = signin(client, EMAILS["org_manager"])
    oid = client.get("/orgs/me/profile", headers=mgr).json()["organization"]["id"]
    fake_clock.advance(minutes=91 * 24 * 60)
    assert client.get("/auth/me", headers=mgr).status_code == 401  # the old session expired
    mgr = signin(client, EMAILS["org_manager"])
    comp = client.get(f"/orgs/{oid}/profile-completeness", headers=mgr).json()
    assert all(q["confirmation_due"] for q in comp["questions"].values())
    after = client.post("/orgs/me/intake/confirm", headers=mgr).json()
    assert not any(q["confirmation_due"] for q in after["questions"].values())
    client.put("/orgs/me/intake/Q2", json={**ORGS["Demo Night Shelter"]["q2"], "typical_nightly_need": 70}, headers=mgr)
    with SessionLocal() as db:
        rows = db.query(IntakeAnswer).filter_by(organization_id=oid, question="Q2").all()
        assert len(rows) == 2 and rows[-1].answers["typical_nightly_need"] == 70  # history kept


def test_ein_change_requires_reverification(client):
    mgr = signin(client, EMAILS["org_manager"])
    oid = client.get("/orgs/me/profile", headers=mgr).json()["organization"]["id"]
    client.put("/orgs/me/intake/Q3", json={**ORGS["Demo Night Shelter"]["q3"], "ein": "00-0000099"}, headers=mgr)
    assert client.get("/orgs/me/profile", headers=mgr).json()["q3"]["ein_verified"] is False
    admin = signin(client, EMAILS["admin"])
    assert client.post(f"/admin/orgs/{oid}/verify-ein", json={"verified": True}, headers=admin).json()["ein_verified"] is True


def test_quick_need_update_and_phone_masking(client):
    staff = signin(client, EMAILS["org_staff"])
    assert client.post("/orgs/me/need", json={"meals": 40}, headers=staff).json()["current_need"] == 40
    assert client.get("/orgs/me/profile", headers=staff).json()["q1"]["receiving_contact_phone"] == "305-555-0102"


@pytest.mark.parametrize("local_time,expected", [
    ("2026-09-25 18:00", (True, None)),              # Friday 6 PM: shelter open 4 PM to midnight
    ("2026-09-25 23:50", (False, "past_cutoff")),    # 15 minute cutoff before midnight
    ("2026-09-26 10:00", (False, "closed")),         # Saturday 10 AM: closed until 4 PM
])
def test_receiving_windows(client, local_time, expected):
    with SessionLocal() as db:
        from app.models import Organization
        shelter = db.query(Organization).filter_by(name="Demo Night Shelter").one()
        p = db.get(ReceiverProfile, shelter.id)
        from app import clock
        at = clock.local_to_utc(datetime.strptime(local_time, "%Y-%m-%d %H:%M"))
        ok, reason = intake.receiving_check(db, p, at)
        assert ok is expected[0]
        assert (reason or {}).get("code") == expected[1]
        if local_time.endswith("10:00"):
            assert reason["text"] == "closed until 4:00 PM"


def test_fridge_is_open_across_midnight_and_food_bank_closed_at_night(client):
    from app import clock
    from app.models import Organization
    with SessionLocal() as db:
        fridge = db.get(ReceiverProfile, db.query(Organization).filter_by(name="Demo Community Fridge").one().id)
        bank = db.get(ReceiverProfile, db.query(Organization).filter_by(name="Demo Food Bank").one().id)
        midnight = clock.local_to_utc(datetime(2026, 9, 26, 0, 30))
        assert intake.receiving_check(db, fridge, midnight) == (True, None)
        ok, reason = intake.receiving_check(db, bank, clock.local_to_utc(datetime(2026, 9, 25, 23, 0)))
        assert not ok and reason["text"] == "closed until 9:00 AM tomorrow"


def test_restaurant_and_volunteer_profiles(client):
    mgr = signin(client, EMAILS["restaurant_manager"])
    body = {"closing_times": {d: "22:00" for d in intake.WEEKDAYS}, "staffed_until": {d: "23:00" for d in intake.WEEKDAYS},
            "totes_on_hand": 4, "hauling_cost_per_lb": 0.08, "public_partner_page": True}
    r = client.put("/restaurants/me/profile", json=body, headers=mgr)
    assert r.status_code == 200 and r.json()["public_slug"]
    assert client.put("/restaurants/me/profile", json={**body, "closing_times": {"mon": "25:00"}}, headers=mgr).status_code == 422
    vol = signin(client, EMAILS["volunteer"])
    v = {"availability": {"mon": [["17:00", "21:00"]]}, "max_distance_mi": 8, "vehicle_description": "Gray SUV"}
    saved = client.put("/volunteers/me/profile", json=v, headers=vol).json()
    assert saved["max_distance_mi"] == 8 and "has_cooler" not in saved  # no equipment questions for drivers
