"""Section 3: quick post, units, safety fields, templates, repeat, recurring drafts, edit/cancel, duplicates."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import clock
from app.assumptions import SAFE_UNTIL_HOURS, UNIT_TO_MEALS
from app.db import SessionLocal
from app.jobs import run_jobs
from app.main import app
from app.models import Notification, Rescue, User
from app.seed import reset_database
from tests.helpers import EMAILS, signin


@pytest.fixture()
def client(fake_clock):
    reset_database(with_scenarios=False)
    with TestClient(app) as c:
        yield c


def body(**kw):
    return {"quantity": 2, "unit": "half_pan", "category": "hot", "attested": True,
            "pickup_deadline": (clock.now() + timedelta(minutes=90)).isoformat() + "Z", **kw}


def test_quick_post_needs_only_four_fields_plus_attestation(client):
    h = signin(client, EMAILS["restaurant_staff"])
    r = client.post("/rescues", json=body(), headers=h)
    assert r.status_code == 200
    x = r.json()["rescue"]
    assert x["unit"] == "half_pan" and x["quantity"] == 2 and x["est_meals"] == 2 * UNIT_TO_MEALS["half_pan"]
    assert x["attested_by"] is not None and x["attested_at"]
    assert x["pickup_instructions"].startswith("Back door")  # default from the restaurant profile
    assert client.post("/rescues", json=body(attested=False), headers=h).status_code == 422
    assert client.post("/rescues", json={k: v for k, v in body().items() if k != "category"}, headers=h).status_code == 422
    assert client.post("/rescues", json=body(unit="bucket"), headers=h).status_code == 422
    assert client.get("/config/assumptions").json()["unit_to_meals"]["kind"] == "assumption"


def test_safe_until_defaults_by_category_and_caps_the_deadline(client, fake_clock):
    h = signin(client, EMAILS["restaurant_staff"])
    for cat in ("hot", "cold", "shelf_stable"):
        x = client.post("/rescues", json=body(category=cat, unit="bag", quantity=1 + len(cat),
                                               pickup_deadline=(clock.now() + timedelta(days=3)).isoformat() + "Z"),
                        headers=h).json()
        from datetime import datetime
        safe = datetime.fromisoformat(x["rescue"]["safe_until"].rstrip("Z"))
        assert safe == clock.now() + timedelta(hours=SAFE_UNTIL_HOURS[cat])
        assert x["rescue"]["pickup_deadline"] == x["rescue"]["safe_until"]  # capped to safe-until
        assert any("safe-until" in w for w in x["warnings"])
    old = body(prepared_at=(clock.now() - timedelta(hours=3)).isoformat() + "Z")
    assert client.post("/rescues", json=old, headers=h).status_code == 422  # hot food prepared 3 h ago


def test_safety_fields_are_stored(client):
    h = signin(client, EMAILS["restaurant_staff"])
    x = client.post("/rescues", json=body(allergens=["dairy", "gluten"], dietary_tags=["vegetarian"],
                                          prepared_at=(clock.now() - timedelta(minutes=30)).isoformat() + "Z"),
                    headers=h).json()["rescue"]
    assert x["allergens"] == ["dairy", "gluten"] and x["allergens_declared"] and x["dietary_tags"] == ["vegetarian"]
    y = client.post("/rescues", json=body(unit="box", quantity=3), headers=h).json()["rescue"]
    assert y["allergens"] is None and y["allergens_declared"] is False  # not declared is different from none


def test_duplicate_warning_within_ten_minutes(client, fake_clock):
    h = signin(client, EMAILS["restaurant_staff"])
    first = client.post("/rescues", json=body(), headers=h).json()["rescue"]
    fake_clock.advance(minutes=4)
    dup = client.post("/rescues", json=body(), headers=h).json()
    assert dup["rescue"]["duplicate_of"] == first["id"] and "looks like rescue" in dup["warnings"][0]
    fake_clock.advance(minutes=11)
    later = client.post("/rescues", json=body(), headers=h).json()
    assert later["rescue"]["duplicate_of"] is None


def test_repeat_last_and_templates(client):
    h = signin(client, EMAILS["restaurant_staff"])
    first = client.post("/rescues", json=body(description="Rice and beans", allergens=[]), headers=h).json()["rescue"]
    rep = client.post("/rescues/repeat-last", json={"attested": True}, headers=h)
    assert rep.status_code == 200
    again = rep.json()["rescue"]
    assert again["description"] == "Rice and beans" and again["id"] != first["id"] and again["allergens"] == []
    assert client.post("/rescues/repeat-last", json={"attested": False}, headers=h).status_code == 422
    t = client.post("/restaurants/me/templates", json={"name": "Friday trays", "post": body(quantity=3, unit="tray")}, headers=h).json()
    assert [x["name"] for x in client.get("/restaurants/me/templates", headers=h).json()] == ["Friday trays"]
    from_t = client.post(f"/rescues/from-template/{t['id']}", json={"attested": True,
                         "pickup_deadline": (clock.now() + timedelta(hours=1)).isoformat() + "Z"}, headers=h)
    assert from_t.status_code == 200 and from_t.json()["rescue"]["est_meals"] == 36


def test_recurring_schedule_creates_a_draft_confirmed_with_one_action(client, fake_clock):
    mgr = signin(client, EMAILS["restaurant_manager"])
    t = client.post("/restaurants/me/templates", json={"name": "Friday 10 PM", "post": body(quantity=2, unit="full_pan")}, headers=mgr).json()
    s = client.post("/restaurants/me/schedules", json={"template_id": t["id"], "weekday": 4, "local_time": "22:00"}, headers=mgr)
    assert s.status_code == 200
    staff_only = signin(client, EMAILS["restaurant_staff"])
    assert client.post("/restaurants/me/schedules", json={"template_id": t["id"], "weekday": 4, "local_time": "22:00"},
                       headers=staff_only).status_code == 403
    with SessionLocal() as db:
        counts = run_jobs(db)  # Friday 7 PM: tonight's 10 PM draft
        assert counts["drafts"] == 1 and run_jobs(db)["drafts"] == 0  # only once per day
        draft = db.query(Rescue).filter_by(is_draft=True).one()
        assert draft.attested_by is None and draft.status == "posted"
    staff = signin(client, EMAILS["restaurant_staff"])
    assert client.post(f"/rescues/{draft.id}/confirm", json={"attested": False}, headers=staff).status_code == 422
    ok = client.post(f"/rescues/{draft.id}/confirm", json={"attested": True}, headers=staff).json()
    assert ok["rescue"]["is_draft"] is False and ok["rescue"]["attested_by"] is not None


def test_edit_and_cancel_until_pickup_notify_the_carrier(client):
    h = signin(client, EMAILS["restaurant_staff"])
    r = client.post("/rescues", json=body(), headers=h).json()["rescue"]
    e = client.patch(f"/rescues/{r['id']}", json={"description": "Chicken and rice"}, headers=h)
    assert e.status_code == 200 and e.json()["changed"] == ["description"]
    c = client.post(f"/rescues/{r['id']}/cancel", json={"reason": "staff ate it"}, headers=h)
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    assert c.json()["trips"][0]["status"] == "cancelled"
    with SessionLocal() as db:
        marcus = db.query(User).filter_by(email=EMAILS["volunteer"]).one()
        events = {n.event for n in db.query(Notification).filter_by(user_id=marcus.id)}
        assert {"offer", "cancelled"} <= events
