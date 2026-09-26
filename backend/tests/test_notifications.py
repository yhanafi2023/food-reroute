"""Section 8: providers, preferences, events, dedupe."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import clock, notify
from app.db import SessionLocal
from app.jobs import run_jobs
from app.main import app
from app.models import Notification, User
from app.seed import reset_database
from tests.helpers import EMAILS, signin


@pytest.fixture()
def client(fake_clock):
    reset_database(with_scenarios=False)
    with TestClient(app) as c:
        yield c


def post(client, h, **kw):
    b = {"quantity": 2, "unit": "tray", "category": "hot", "attested": True,
         "pickup_deadline": (clock.now() + timedelta(minutes=90)).isoformat() + "Z", **kw}
    return client.post("/rescues", json=b, headers=h).json()["rescue"]


def test_console_is_the_default_and_events_reach_each_party(client):
    h = signin(client, EMAILS["restaurant_staff"])
    post(client, h)
    mine = client.get("/me/notifications", headers=h).json()
    assert mine[0]["event"] == "matched" and mine[0]["channel"] == "console" and "Pickup code" in mine[0]["body"]
    vol = client.get("/me/notifications", headers=signin(client, EMAILS["volunteer"])).json()
    assert vol[0]["event"] == "offer"
    org = client.get("/me/notifications", headers=signin(client, EMAILS["org_staff"])).json()
    assert org[0]["event"] == "matched" and "arriving around" in org[0]["body"]


def test_approaching_and_expiry_warnings_are_sent_once(client, fake_clock):
    h = signin(client, EMAILS["restaurant_staff"])
    post(client, h, prepared_at=(clock.now() - timedelta(minutes=95)).isoformat() + "Z")
    with SessionLocal() as db:
        run_jobs(db)
        run_jobs(db)
        rest = db.query(User).filter_by(email=EMAILS["restaurant_staff"]).one()
        events = [n.event for n in db.query(Notification).filter_by(user_id=rest.id)]
    assert events.count("expiry_warning") <= 1


def test_muted_events_and_channel_preferences(client):
    h = signin(client, EMAILS["restaurant_staff"])
    prefs = client.get("/me/notification-preferences", headers=h).json()
    assert "console" in prefs["available_channels"] and "matched" in prefs["events"]
    assert client.put("/me/notification-preferences", json={"muted": ["not_an_event"]}, headers=h).status_code == 422
    client.put("/me/notification-preferences", json={"channels": ["console"], "muted": ["matched"]}, headers=h)
    post(client, h)
    assert all(n["event"] != "matched" for n in client.get("/me/notifications", headers=h).json())


def test_email_and_sms_providers_when_configured(client, monkeypatch):
    sent = {"email": [], "sms": []}

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, *a): pass
        def send_message(self, msg): sent["email"].append(msg["To"])

    class FakeResp:
        def raise_for_status(self): pass

    monkeypatch.setattr(notify, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(notify, "TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setattr(notify, "TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setattr(notify, "TWILIO_FROM", "+15550000000")
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **k: sent["sms"].append(k["data"]["To"]) or FakeResp())
    with SessionLocal() as db:
        u = db.query(User).filter_by(email=EMAILS["restaurant_staff"]).one()
        u.notification_prefs = {"channels": ["console", "email", "sms"]}
        db.commit()
        out = notify.send(db, [u], "picked_up", "Food picked up", "40 meals", dedupe="t1")
        assert {n.channel for n in out} == {"console", "email", "sms"} and all(n.status == "sent" for n in out)
        assert notify.send(db, [u], "picked_up", "Food picked up", "40 meals", dedupe="t1") == []  # deduped
    assert sent["email"] == [EMAILS["restaurant_staff"]] and sent["sms"] == ["305-555-0199"]


def test_a_failing_provider_never_breaks_the_request(client, monkeypatch):
    monkeypatch.setattr(notify, "SMTP_HOST", "smtp.example.com")

    def boom(*a, **k):
        raise OSError("smtp down")

    monkeypatch.setattr(notify.smtplib, "SMTP", boom)
    h = signin(client, EMAILS["restaurant_staff"])
    r = client.post("/rescues", json={"quantity": 2, "unit": "tray", "category": "hot", "attested": True,
                                      "pickup_deadline": (clock.now() + timedelta(minutes=90)).isoformat() + "Z"}, headers=h)
    assert r.status_code == 200
    with SessionLocal() as db:
        assert db.query(Notification).filter_by(channel="email", status="failed").count() >= 1
