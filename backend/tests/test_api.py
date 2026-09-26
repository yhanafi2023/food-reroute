"""Dev 2 tests: the full demo flow through the API, role checks, and illegal status jumps."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seed import reset_database


@pytest.fixture()
def client():
    reset_database()
    with TestClient(app) as c:
        yield c


def login(client, email):
    r = client.post("/auth/login", json={"email": email, "password": "demo1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def future(minutes=180):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


RESCUE = {"food_type": "Rice, beans and chicken", "meals": 50, "weight_lbs": 60, "time_sensitivity": "MEDIUM",
          "description": "Trays from dinner service", "food_safety_confirmed": True}


def test_full_demo_flow(client):
    rest, drv, org, shelter, admin = (login(client, e) for e in (
        "restaurant@demo.com", "driver@demo.com", "org@demo.com", "shelter@demo.com", "admin@demo.com"))
    before = client.get("/impact").json()
    assert before["includes_demo_data"] is True

    r = client.post("/rescues", json={**RESCUE, "pickup_deadline": future()}, headers=rest)
    assert r.status_code == 200, r.text
    rescue, match = r.json()["rescue"], r.json()["match"]
    assert rescue["status"] == "MATCHED"
    assert match["driver"]["name"] == "Marcus"
    assert {(s["name"], s["meals"]) for s in match["stops"]} == {("Community Food Bank", 30), ("Hope Shelter", 20)}
    assert match["top_candidates"] and match["reasons"]

    offer = client.get("/drivers/dashboard", headers=drv).json()["offer"]
    assert offer["rescue"]["id"] == rescue["id"]

    d = client.post(f"/rescues/{rescue['id']}/accept", headers=drv)
    assert d.status_code == 200, d.text
    delivery = d.json()
    assert delivery["status"] == "HEADING_TO_RESTAURANT"
    assert delivery["route"]["source"] == "offline" and len(delivery["route"]["geometry"]) >= 2
    assert client.get("/drivers/dashboard", headers=drv).json()["driver"]["is_available"] is False

    # confirming before delivery is refused
    assert client.post(f"/deliveries/{delivery['id']}/confirm", headers=org).status_code == 400

    for status in ("ARRIVED_AT_RESTAURANT", "PICKED_UP", "DELIVERING", "DELIVERED"):
        r = client.patch(f"/deliveries/{delivery['id']}/status", json={"status": status}, headers=drv)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == status
    assert client.get(f"/rescues/{rescue['id']}", headers=rest).json()["rescue"]["status"] == "DELIVERED"

    incoming = client.get("/organizations/dashboard", headers=org).json()["incoming"]
    assert incoming[0]["my_meals"] == 30 and incoming[0]["can_confirm"]

    r = client.post(f"/deliveries/{delivery['id']}/confirm", headers=org)
    assert r.status_code == 200 and r.json()["status"] == "DELIVERED"  # shelter has not confirmed yet
    assert client.post(f"/deliveries/{delivery['id']}/confirm", headers=org).status_code == 400
    r = client.post(f"/deliveries/{delivery['id']}/confirm", headers=shelter)
    assert r.status_code == 200 and r.json()["status"] == "CONFIRMED"

    after = client.get("/impact").json()
    assert after["meals_rescued"] == before["meals_rescued"] + 50
    assert after["deliveries_completed"] == before["deliveries_completed"] + 1
    needs = client.get("/organizations/needs", headers=org).json()
    assert any(n["status"] == "FULFILLED" and n["meals_fulfilled"] == 30 for n in needs)
    stats = client.get("/restaurants/dashboard", headers=rest).json()["stats"]
    assert stats["completed"] == 1 and stats["meals_donated"] == 50

    net = client.get("/admin/network", headers=admin).json()
    assert len(net["restaurants"]) == 6 and len(net["drivers"]) == 5 and len(net["organizations"]) == 4


def test_decline_rematches_to_another_driver(client):
    rest, drv = login(client, "restaurant@demo.com"), login(client, "driver@demo.com")
    rescue = client.post("/rescues", json={**RESCUE, "pickup_deadline": future()}, headers=rest).json()["rescue"]
    r = client.post(f"/rescues/{rescue['id']}/decline", headers=drv)
    assert r.status_code == 200
    assert r.json()["match"]["driver"]["name"] != "Marcus"
    assert client.get("/drivers/dashboard", headers=drv).json()["offer"] is None


def test_wrong_roles_get_403(client):
    rest, drv, org = login(client, "restaurant@demo.com"), login(client, "driver@demo.com"), login(client, "org@demo.com")
    assert client.post("/rescues", json={**RESCUE, "pickup_deadline": future()}, headers=drv).status_code == 403
    assert client.get("/admin/network", headers=rest).status_code == 403
    assert client.post("/demo/reset", headers=org).status_code == 403
    assert client.post("/matching/run", headers=drv).status_code == 403
    assert client.get("/drivers/dashboard", headers=org).status_code == 403
    assert client.get("/admin/network").status_code == 401


def test_other_driver_cannot_touch_delivery(client):
    rest, drv = login(client, "restaurant@demo.com"), login(client, "driver@demo.com")
    other = login(client, "aisha@demo.com")
    rescue = client.post("/rescues", json={**RESCUE, "pickup_deadline": future()}, headers=rest).json()["rescue"]
    assert client.post(f"/rescues/{rescue['id']}/accept", headers=other).status_code == 409
    delivery = client.post(f"/rescues/{rescue['id']}/accept", headers=drv).json()
    r = client.patch(f"/deliveries/{delivery['id']}/status", json={"status": "ARRIVED_AT_RESTAURANT"}, headers=other)
    assert r.status_code == 403


def test_illegal_status_jump_is_400(client):
    rest, drv = login(client, "restaurant@demo.com"), login(client, "driver@demo.com")
    rescue = client.post("/rescues", json={**RESCUE, "pickup_deadline": future()}, headers=rest).json()["rescue"]
    delivery = client.post(f"/rescues/{rescue['id']}/accept", headers=drv).json()
    r = client.patch(f"/deliveries/{delivery['id']}/status", json={"status": "DELIVERED"}, headers=drv)
    assert r.status_code == 400 and "next step is ARRIVED_AT_RESTAURANT" in r.json()["detail"]
    r = client.patch(f"/deliveries/{delivery['id']}/status", json={"status": "CONFIRMED"}, headers=drv)
    assert r.status_code == 400


def test_validation(client):
    rest = login(client, "restaurant@demo.com")
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert client.post("/rescues", json={**RESCUE, "pickup_deadline": past}, headers=rest).status_code == 422
    assert client.post("/rescues", json={**RESCUE, "meals": 0, "pickup_deadline": future()}, headers=rest).status_code == 422
    body = {**RESCUE, "food_safety_confirmed": False, "pickup_deadline": future()}
    assert client.post("/rescues", json=body, headers=rest).status_code == 422


def test_signup_login_me(client):
    r = client.post("/auth/signup", json={"name": "New Kitchen", "email": "new@kitchen.com", "password": "longpassword",
                                          "role": "RESTAURANT", "lat": 25.76, "lng": -80.37})
    assert r.status_code == 200
    token = r.json()["token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["role"] == "RESTAURANT"
    assert client.post("/auth/signup", json={"name": "X", "email": "new@kitchen.com", "password": "longpassword",
                                             "role": "DRIVER"}).status_code == 409
    assert client.post("/auth/signup", json={"name": "X", "email": "x@x.com", "password": "longpassword",
                                             "role": "ADMIN"}).status_code == 422
    assert client.post("/auth/login", json={"email": "new@kitchen.com", "password": "wrong-pass"}).status_code == 401


def test_admin_batch_matching_simulation_and_ml(client):
    admin = login(client, "admin@demo.com")
    r = client.post("/matching/run", headers=admin)
    assert r.status_code == 200 and r.json()["matched"] == 1  # the expiring soon bakery rescue
    assert any("deadline" in reason for reason in r.json()["matches"][0]["reasons"])

    sim1 = client.post("/simulation/run", headers=admin).json()
    sim2 = client.post("/simulation/run", headers=admin).json()
    assert sim1 == sim2 and sim1["label"] == "Simulated data"
    types = {e["type"] for e in sim1["events"]}
    assert {"rescue_posted", "matched", "delivered"} <= types
    assert all(e["t_ms"] <= sim1["duration_ms"] for e in sim1["events"])
    first = next(e for e in sim1["events"] if e["type"] == "matched")
    assert len(first["stops"]) == 2

    forecast = client.get("/ml/forecast", headers=admin).json()
    assert len(forecast["forecast"]) == 6 and "synthetic" in forecast["label"]
    assert client.get("/ml/info").json()["data"] == "prototype trained on synthetic data"
    p = client.post("/ml/predict", json={"day_of_week": 5, "hour": 21, "food_category": "buffet"}, headers=admin).json()
    assert 0 <= p["probability"] <= 1


def test_reset_is_fast_and_exact(client):
    import time
    admin = login(client, "admin@demo.com")
    client.post("/matching/run", headers=admin)
    start = time.perf_counter()
    assert client.post("/demo/reset", headers=admin).status_code == 200
    assert time.perf_counter() - start < 2.0
    net = client.get("/admin/network", headers=login(client, "admin@demo.com")).json()
    assert net["stats"]["open_rescues"] == 1 and net["stats"]["available_drivers"] == 5
