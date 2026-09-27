# A signed-in driver can find work right away: "I'm free now", the open-rescue list, and claiming one
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import clock
from app.db import SessionLocal
from app.main import app
from app.models import Organization, RestaurantProfile, VolunteerProfile
from app.seed import reset_database
from tests.helpers import EMAILS, signin


@pytest.fixture()
def client(fake_clock):
    reset_database(with_scenarios=False)
    with SessionLocal() as db:
        # nobody is on their weekly schedule, and Casa has no curbside staff, so no simulated vehicle
        # can take the food either: a posted rescue stays open until a volunteer steps up
        for v in db.query(VolunteerProfile).all():
            v.availability = {}
        casa = db.query(Organization).filter_by(name="Casa Demo Cocina").one()
        db.get(RestaurantProfile, casa.id).staffed_until = {}
        db.commit()
    with TestClient(app) as c:
        yield c


def post_open(client):
    h = signin(client, EMAILS["restaurant_staff"])
    r = client.post("/rescues", headers=h, json={
        "quantity": 2, "unit": "tray", "attested": True, "description": "Rice and beans",
        "pickup_deadline": (clock.now() + timedelta(minutes=90)).isoformat() + "Z"})
    assert r.status_code == 200, r.text
    rescue = r.json()["rescue"]
    assert rescue["status"] == "posted" and not rescue["trips"]
    return rescue


def test_open_rescues_list_what_a_volunteer_can_take(client):
    rid = post_open(client)["id"]
    h = signin(client, EMAILS["volunteer"])
    body = client.get("/volunteers/me/open-rescues", headers=h).json()
    mine = [r for r in body["rescues"] if r["id"] == rid]
    assert mine and mine[0]["can_take"] and mine[0]["restaurant"]["name"] == "Casa Demo Cocina"
    assert body["available_now"] is False and body["busy"] is False


def test_free_now_offers_the_open_rescue_at_once(client):
    rid = post_open(client)["id"]
    h = signin(client, EMAILS["volunteer"])
    r = client.post("/volunteers/me/availability", headers=h, json={"minutes": 60})
    assert r.status_code == 200, r.text
    assert r.json()["offered_rescue_id"] == rid and r.json()["available_now"]
    offers = client.get("/volunteers/me/trips", headers=h).json()["offers"]
    assert [t["rescue_id"] for t in offers] == [rid]

    off = client.post("/volunteers/me/availability", headers=h, json={"minutes": 0}).json()
    assert off["available_until"] is None


def test_claim_matches_and_accepts_in_one_step(client):
    rid = post_open(client)["id"]
    h = signin(client, EMAILS["volunteer"])
    r = client.post(f"/volunteers/me/open-rescues/{rid}/claim", headers=h, json={})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "en_route_pickup"
    assert client.get("/volunteers/me/trips", headers=h).json()["active"][0]["rescue_id"] == rid

    again = client.post(f"/volunteers/me/open-rescues/{rid}/claim", headers=h, json={})
    assert again.status_code == 409  # already on a trip
    other = signin(client, "sam@volunteer-demo.example.com")
    taken = client.post(f"/volunteers/me/open-rescues/{rid}/claim", headers=other, json={})
    assert taken.status_code == 409 and "already took" in taken.json()["detail"]


def test_claim_explains_why_a_driver_cannot_take_it(client):
    rid = post_open(client)["id"]
    h = signin(client, "aisha@volunteer-demo.example.com")
    with SessionLocal() as db:  # she only drives half a mile from home
        from app.models import User
        aisha = db.query(User).filter_by(email="aisha@volunteer-demo.example.com").one()
        db.get(VolunteerProfile, aisha.id).max_distance_mi = 0.5
        db.commit()
    r = client.post(f"/volunteers/me/open-rescues/{rid}/claim", headers=h, json={})
    assert r.status_code == 409 and "maximum distance" in r.json()["detail"]


def test_any_driver_on_the_job_can_take_any_food(client):
    rid = post_open(client)["id"]
    h = signin(client, "aisha@volunteer-demo.example.com")
    with SessionLocal() as db:  # no bags, no cooler, a tiny car: none of it matters any more
        from app.models import User
        aisha = db.query(User).filter_by(email="aisha@volunteer-demo.example.com").one()
        v = db.get(VolunteerProfile, aisha.id)
        v.has_cooler = v.has_insulated_bags = False
        v.capacity_meals = 1
        db.commit()
    listed = client.get("/volunteers/me/open-rescues", headers=h).json()["rescues"]
    assert [r["can_take"] for r in listed if r["id"] == rid] == [True]
    assert client.post(f"/volunteers/me/open-rescues/{rid}/claim", headers=h, json={}).status_code == 200


def test_restaurants_and_orgs_must_give_an_address(client):
    r = client.post("/auth/register-organization", json={
        "kind": "restaurant", "organization_name": "No Address Cafe", "lat": 25.76, "lng": -80.37,
        "manager_name": "No Address", "manager_email": "na@cafe.example.com", "manager_password": "na-password-1"})
    assert r.status_code == 422 and "address" in r.text


def test_a_failed_claim_says_exactly_why(client):
    h = signin(client, EMAILS["restaurant_staff"])
    r = client.post("/rescues", headers=h, json={
        "quantity": 2, "unit": "tray", "attested": True,
        "pickup_deadline": (clock.now() + timedelta(minutes=1)).isoformat() + "Z"}).json()["rescue"]
    drv = signin(client, "sam@volunteer-demo.example.com")  # lives about 2 miles away: cannot be there in a minute
    res = client.post(f"/volunteers/me/open-rescues/{r['id']}/claim", headers=drv, json={})
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert "after its pickup deadline" in detail and "registered nearby" not in detail, detail


def test_driver_can_cancel_a_taken_trip_before_pickup(client):
    rid = post_open(client)["id"]
    h = signin(client, EMAILS["volunteer"])
    trip = client.post(f"/volunteers/me/open-rescues/{rid}/claim", headers=h, json={}).json()
    assert client.post(f"/trips/{trip['id']}/cancel", headers=h).status_code == 200
    mine = client.get("/volunteers/me/trips", headers=h).json()
    assert not mine["active"] and not mine["offers"]  # free to take something else
    rest = signin(client, EMAILS["restaurant_staff"])
    assert client.get(f"/rescues/{rid}", headers=rest).json()["requeue_count"] == 1  # FoodFlow looks for another driver
