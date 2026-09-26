"""Section 11: coverage, matching rejections, and the deterministic fleet comparison."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import clock
from app.fleet_sim import run
from app.main import app
from app.seed import reset_database
from tests.helpers import EMAILS, signin


@pytest.fixture()
def client(fake_clock):
    reset_database(with_scenarios=False)
    with TestClient(app) as c:
        yield c


def test_matching_rejections_show_the_intake_answers_working(client):
    h = signin(client, EMAILS["restaurant_staff"])
    client.post("/rescues", json={"quantity": 2, "unit": "tray", "category": "hot", "attested": True,
                                  "pickup_deadline": (clock.now() + timedelta(minutes=90)).isoformat() + "Z"}, headers=h)
    admin = signin(client, EMAILS["admin"])
    rej = client.get("/analytics/matching-rejections", headers=admin).json()
    assert rej["by_reason_group"]["no_hot_food"] == 2      # food bank and fridge said no hot food
    assert rej["by_reason_group"]["closed"] >= 1           # food bank closed at 7 PM
    assert rej["by_reason_group"]["dietary"] == 1          # halal pantry
    cov = client.get("/analytics/coverage", headers=admin).json()
    assert cov["by_hour_local"][0]["hour"] == 19
    assert client.get("/analytics/coverage", headers=h).status_code == 403


def test_fleet_simulation_is_deterministic_and_reports_real_numbers():
    a1, a2 = run("mixed_fleet"), run("mixed_fleet")
    assert a1 == a2
    v = run("volunteer_only")
    assert v["meals_posted"] == a1["meals_posted"] and v["rescues_posted"] == a1["rescues_posted"] == 14
    assert "waymo_sim" not in v["meals_delivered_by_mode"] and "robot_sim" not in v["meals_delivered_by_mode"]
    for r in (v, a1):
        assert r["meals_delivered"] + r["meals_expired"] + r["meals_not_delivered_other"] <= r["meals_posted"]
