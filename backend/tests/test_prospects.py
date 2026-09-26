"""Prospect directory: data integrity, filters, the seven-day log, and ranking rules."""
import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import prospects
from app.main import app
from app.seed import reset_database
from tests.helpers import EMAILS, signin

URL = re.compile(r"^https://")
CHECKED = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@pytest.fixture()
def client():
    reset_database(with_scenarios=False)
    with TestClient(app) as c:
        yield c


def auth(client, email):
    return signin(client, {"restaurant@demo.com": EMAILS["restaurant_staff"], "admin@demo.com": EMAILS["admin"]}[email])


def test_every_prospect_is_sourced_and_honest():
    data = prospects.load()
    assert data["prospects"], "directory is empty"
    for p in data["prospects"]:
        assert p["sources"], p["id"]
        for s in p["sources"] + p["evidence"]:
            assert URL.match(s["url"]) and CHECKED.match(s["checked"]), (p["id"], s)
        assert p["evidence_strength"] in prospects.EVIDENCE_LEVELS
        # evidence level must match the evidence actually recorded
        if p["evidence_strength"] == "none_found":
            assert p["evidence"] == []
        else:
            assert any(e["type"] == p["evidence_strength"] for e in p["evidence"])
        # nothing measured unless a quantity AND a period AND a source are documented
        m = p["surplus_measurement"]
        assert m is None or (m.get("meals") is not None and m.get("period_days") and URL.match(m.get("url", "")))
        assert p["evidence_strength"] != "measured" or m is not None
        text = " ".join([p.get("address_note") or ""] + [e["summary"] for e in p["evidence"]]).lower()
        assert "throws away" not in text and "wastes a lot" not in text


def test_three_named_prospects_are_present():
    names = {p["id"]: p for p in prospects.all_prospects()}
    assert names["macchialina"]["evidence_strength"] == "documented_donation"
    assert names["bodeguita-coral-way"]["address"].startswith("7403 Coral Way")
    assert names["mia-bakery-gourmet"]["address"].startswith("2100 NW 107th Avenue, Suite 110")
    assert all(p["enrollment_status"] == "not_enrolled" for p in names.values())


def test_directory_is_admin_only_and_filters(client):
    assert client.get("/prospects", headers=auth(client, "restaurant@demo.com")).status_code == 403
    admin = auth(client, "admin@demo.com")
    everything = client.get("/prospects", headers=admin).json()
    assert everything["total"] == len(everything["items"])
    miles = [p["miles_from_fiu"] for p in everything["items"]]
    assert miles == sorted(miles)  # nearest to FIU first
    doral = client.get("/prospects", params={"neighborhood": "Doral"}, headers=admin).json()["items"]
    assert doral and all(p["neighborhood"] == "Doral" for p in doral)
    listed = client.get("/prospects", params={"evidence": ["marketplace_listing"]}, headers=admin).json()["items"]
    assert listed and all(p["evidence_strength"] == "marketplace_listing" for p in listed)
    near = client.get("/prospects", params={"max_miles": 3}, headers=admin).json()["items"]
    assert all(p["miles_from_fiu"] <= 3 for p in near)
    assert client.get("/prospects", params={"q": "macchia"}, headers=admin).json()["items"][0]["id"] == "macchialina"
    meta = client.get("/prospects/meta", headers=admin).json()
    assert "Doral" in meta["neighborhoods"] and meta["reference_point"]["name"].startswith("FIU")


def test_nothing_is_ranked_without_measurement(client):
    admin = auth(client, "admin@demo.com")
    result = client.get("/prospects/opportunities", headers=admin).json()
    assert result["ranked"] == []
    assert len(result["not_ranked"]) == len(prospects.all_prospects())
    assert all("seven-day log" in r["reason"] for r in result["not_ranked"])


def _day(i, meals, disposition="discarded", safe=True):
    return {"log_date": (date.today() - timedelta(days=7 - i)).isoformat(), "surplus_meals": meals, "surplus_lbs": meals * 1.1,
            "safe_to_donate": safe, "disposition": disposition, "food_categories": "rice, beans", "ready_time": "21:30"}


def test_seven_day_log_makes_a_prospect_rankable(client):
    admin = auth(client, "admin@demo.com")
    pid = "sergios-fiu"
    for i in range(6):
        client.put(f"/prospects/{pid}/surplus-log", json=_day(i, 12), headers=admin)
    partial = client.get("/prospects/opportunities", headers=admin).json()
    assert partial["ranked"] == []
    assert any(r["id"] == pid and "6 of 7" in r["reason"] for r in partial["not_ranked"])

    r = client.put(f"/prospects/{pid}/surplus-log", json=_day(6, 0, "no_surplus", False), headers=admin)
    summary = r.json()["summary"]
    assert summary["complete"] and summary["recoverable_meals"] == 72 and summary["recoverable_days"] == 6

    ranked = client.get("/prospects/opportunities", headers=admin).json()["ranked"]
    assert ranked[0]["id"] == pid and ranked[0]["recoverable_meals_per_week"] == 72
    assert ranked[0]["pickups_per_week"] == 6 and "Self-reported" in ranked[0]["basis"]


def test_existing_commitments_rank_after_uncommitted(client):
    admin = auth(client, "admin@demo.com")
    for i in range(7):
        client.put("/prospects/macchialina/surplus-log", json=_day(i, 30), headers=admin)  # bigger, but already a donor
        client.put("/prospects/cuban-guys-flagler/surplus-log", json=_day(i, 10), headers=admin)
    ranked = client.get("/prospects/opportunities", headers=admin).json()["ranked"]
    assert [r["id"] for r in ranked] == ["cuban-guys-flagler", "macchialina"]
    assert ranked[1]["existing_commitments"] == ["Food Rescue US - South Florida"]


def test_log_validation_and_restaurant_self_logging(client):
    admin = auth(client, "admin@demo.com")
    bad = {**_day(0, 5), "disposition": "no_surplus"}
    assert client.put("/prospects/sergios-fiu/surplus-log", json=bad, headers=admin).status_code == 422
    future = {**_day(0, 5), "log_date": (date.today() + timedelta(days=2)).isoformat()}
    assert client.put("/prospects/sergios-fiu/surplus-log", json=future, headers=admin).status_code == 422
    assert client.put("/prospects/not-a-place/surplus-log", json=_day(0, 5), headers=admin).status_code == 404

    rest = auth(client, "restaurant@demo.com")
    for i in range(7):
        assert client.put("/restaurants/me/surplus-log", json=_day(i, 8), headers=rest).status_code == 200
    mine = client.get("/restaurants/me/surplus-log", headers=rest).json()
    assert mine["summary"]["complete"] and mine["summary"]["recoverable_meals"] == 56
    ranked = client.get("/prospects/opportunities", headers=admin).json()["ranked"]
    partner = next(r for r in ranked if r["kind"] == "enrolled_partner")
    assert partner["is_demo"] is True and partner["name"] == "Casa Demo Cocina"  # fictional demo partner
