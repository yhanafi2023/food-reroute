#Given this food donation, which organizations can recieve it, which can't, and can the system explain why/what happened
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import clock
from app.db import SessionLocal
from app.main import app
from app.models import Organization, ReceiverProfile
from app.seed import reset_database
from tests.helpers import EMAILS, signin


@pytest.fixture()
def client(fake_clock):
    reset_database(with_scenarios=False)
    with TestClient(app) as c:
        yield c


def post(client, h, **kw):
    b = {"quantity": 2, "unit": "tray", "attested": True,
         "pickup_deadline": (clock.now() + timedelta(minutes=90)).isoformat() + "Z", **kw}
    r = client.post("/rescues", json=b, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["rescue"]


def explain(client, h, rid):
    e = client.get(f"/rescues/{rid}/matching-explanation", headers=h).json()
    return e, {x["name"]: x for x in e["ineligible"]}, {x["name"] for x in e["eligible"]}


def test_friday_7pm_explanations_come_from_intake_answers(client):
    h = signin(client, EMAILS["restaurant_staff"])
    r = post(client, h)  # 24 meals, no dietary tags, allergens not declared
    e, bad, good = explain(client, h, r["id"])
    # any kind of food goes anywhere that is open, has room and whose dietary rules it meets
    assert good == {"Demo Night Shelter", "Demo Community Fridge"}
    assert bad["Demo Food Bank"]["groups"] == ["closed"]  # 7 PM Friday: closed at 5 PM
    halal = {x["code"] for x in bad["Demo Halal Pantry"]["reasons"]}
    assert {"dietary", "allergens_undeclared", "curbside"} >= halal and "dietary" in halal
    assert {s["organization"]["name"] for t in r["trips"] for s in t["stops"]} <= good


def test_food_bank_is_closed_at_night_and_explains_when_it_opens(client, fake_clock):
    fake_clock.advance(minutes=3 * 60)  # Friday 10 PM
    h = signin(client, EMAILS["restaurant_staff"])
    r = post(client, h, unit="box", quantity=3)
    _, bad, good = explain(client, h, r["id"])
    assert "closed until 9:00 AM tomorrow" in [x["text"] for x in bad["Demo Food Bank"]["reasons"]]
    assert "Demo Community Fridge" in good  # 24/7


def test_halal_pantry_eligible_only_for_declared_halal_peanut_free_food(client, fake_clock):
    fake_clock.advance(minutes=-4 * 60)  # Friday 3 PM: pantry open, shelter not yet
    h = signin(client, EMAILS["restaurant_staff"])
    r = post(client, h, unit="bag", quantity=4, dietary_tags=["halal"], allergens=["dairy"])
    _, bad, good = explain(client, h, r["id"])
    assert "Demo Halal Pantry" in good
    r2 = post(client, h, unit="bag", quantity=5, dietary_tags=["halal"], allergens=["peanuts"])
    _, bad2, _ = explain(client, h, r2["id"])
    assert any(x["text"] == "does not accept peanuts" for x in bad2["Demo Halal Pantry"]["reasons"])


def test_food_type_plays_no_part(client):
    h = signin(client, EMAILS["restaurant_staff"])
    r = post(client, h, category="frozen")  # an old client still sending a category: ignored
    assert "category" not in r
    _, bad, good = explain(client, h, r["id"])
    assert all(g not in ("no_hot_food", "hot_too_slow", "category") for b in bad.values() for g in b["groups"])
    with SessionLocal() as db:
        from app.models import Rescue
        assert db.get(Rescue, r["id"]).category == "general"


def test_capacity_and_tonights_need(client):
    org = signin(client, EMAILS["org_staff"])
    client.post("/orgs/me/need", json={"meals": 0}, headers=org)
    h = signin(client, EMAILS["restaurant_staff"])
    r = post(client, h)
    _, bad, _ = explain(client, h, r["id"])
    assert bad["Demo Night Shelter"]["reasons"][0]["code"] == "need_met"
    client.post("/orgs/me/need", json={"meals": 10}, headers=org)
    r2 = post(client, h, unit="box", quantity=3)
    stops = [s for t in r2["trips"] for s in t["stops"]]
    assert sum(s["allocated_meals"] for s in stops if s["organization"]["name"] == "Demo Night Shelter") <= 10


def test_incomplete_org_receives_nothing(client):
    client.post("/auth/register-organization", json={"kind": "receiver", "organization_name": "Brand New Shelter", "address": "400 Test St, Miami FL",
               "lat": 25.762, "lng": -80.369, "manager_name": "New Manager", "manager_email": "new@shelter.example.com",
               "manager_password": "new-manager-password"})
    h = signin(client, EMAILS["restaurant_staff"])
    r = post(client, h)
    _, bad, good = explain(client, h, r["id"])
    assert "Brand New Shelter" not in good
    assert bad["Brand New Shelter"]["reasons"] == [{"code": "onboarding_incomplete",
                                                    "text": "has not finished the three onboarding questions"}]


def test_drivers_need_no_special_equipment(client):
    from app.models import VolunteerProfile
    with SessionLocal() as db:
        for v in db.query(VolunteerProfile).all():
            v.has_cooler = v.has_insulated_bags = False
            v.capacity_meals = 1
        db.commit()
    h = signin(client, EMAILS["restaurant_staff"])
    r = post(client, h, unit="bag", quantity=3)
    assert any(t["mode"] == "volunteer" for t in r["trips"])  # no cooler, bags or room needed


def test_matching_explanation_is_for_restaurant_and_admin(client):
    h = signin(client, EMAILS["restaurant_staff"])
    r = post(client, h)
    assert client.get(f"/rescues/{r['id']}/matching-explanation", headers=signin(client, EMAILS["admin"])).status_code == 200
    assert client.get(f"/rescues/{r['id']}/matching-explanation", headers=signin(client, EMAILS["org_staff"])).status_code == 403


# ---------- community need (Census-derived matching factor) ----------

def test_eligible_organizations_carry_a_ranked_score_breakdown(client):
    """Community need is one scored factor among several, computed only for
    organizations eligibility.check has already let through -- never a hard gate."""
    h = signin(client, EMAILS["restaurant_staff"])
    r = post(client, h, unit="box", quantity=10)
    e, _, good = explain(client, h, r["id"])
    assert good == {"Demo Community Fridge", "Demo Night Shelter"}
    for x in e["eligible"]:
        assert x["score"].keys() >= {"distance_score", "urgency_score", "demand_score", "capacity_score",
                                     "community_need_score", "total"}
        assert all(0.0 <= v <= 1.0 for k, v in x["score"].items() if k.endswith("_score") or k == "total")
    ranks = [x["rank"] for x in e["eligible"]]
    assert ranks == list(range(1, len(ranks) + 1))
    assert [x["rank"] for x in e["eligible"]] == sorted(
        range(1, len(ranks) + 1), key=lambda i: -e["eligible"][i - 1]["score"]["total"])


def test_what_if_community_priority_reweights_without_changing_eligibility(client):
    h = signin(client, EMAILS["restaurant_staff"])
    r = post(client, h, unit="box", quantity=10)
    standard = client.get(f"/rescues/{r['id']}/matching-explanation", headers=h).json()
    priority = client.get(f"/rescues/{r['id']}/matching-explanation?weights=community_need_priority", headers=h).json()
    assert priority["weights_used"] == "community_need_priority"
    std_ids = {x["organization_id"] for x in standard["eligible"]}
    pri_ids = {x["organization_id"] for x in priority["eligible"]}
    assert std_ids == pri_ids  # re-weighting never changes who is feasible, only the ranking
    std_totals = {x["organization_id"]: x["score"]["total"] for x in standard["eligible"]}
    pri_totals = {x["organization_id"]: x["score"]["total"] for x in priority["eligible"]}
    assert std_totals != pri_totals  # but it does change the numbers


def test_community_need_endpoints(client):
    h = signin(client, EMAILS["restaurant_staff"])
    areas = client.get("/community-need/areas", headers=h).json()
    assert areas["source"].startswith("U.S. Census Bureau")
    assert len(areas["areas"]) > 0
    assert {a["bucket"] for a in areas["areas"]} <= {"low", "moderate", "high", "very_high"}

    from app.models import Organization
    with SessionLocal() as db:
        shelter = db.query(Organization).filter_by(name="Demo Night Shelter").one()
    need = client.get(f"/community-need/organizations/{shelter.id}", headers=h).json()
    assert need["community_need"]["bucket"] in ("low", "moderate", "high", "very_high")
    assert "does not describe individual residents" in need["disclaimer"]
