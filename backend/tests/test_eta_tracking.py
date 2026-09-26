"""ETA model trained on real OSRM data, live tracking, GPS sharing, trip-leg logging."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.intelligence.eta.features import HANDLING_MINUTES_PER_STOP
from app.intelligence.eta.model import ensure_eta_model, predict_legs
from app.main import app
from app.models import Delivery, TripLeg
from app.db import SessionLocal
from app.seed import reset_database
from app.tracking import point_along

FIU = (25.761086, -80.376253)
BIRD_ROAD = (25.732782, -80.346367)
MACCHIALINA = (25.778428, -80.140906)


def test_model_beats_the_old_rule_on_new_places():
    m = ensure_eta_model()["metrics"]
    assert m["mae_minutes"]["hist_gradient_boosting"] < m["mae_minutes"]["rule_22mph"]
    assert 0.6 <= m["p10_p90_coverage"] <= 0.95  # calibrated range on held-out points
    assert m["n_test_pairs"] > 1000


def test_predictions_are_ordered_and_sensible():
    near, far = predict_legs([(FIU, BIRD_ROAD, 0), (FIU, MACCHIALINA, 0)])
    for p in (near, far):
        assert p["p10"] <= p["p50"] <= p["p90"] and p["source"] == "ml"
    assert far["p50"] > near["p50"] + 5  # Miami Beach is much farther by road than Westchester
    with_stop = predict_legs([(FIU, BIRD_ROAD, 1)])[0]
    assert with_stop["p50"] == pytest.approx(near["p50"] + HANDLING_MINUTES_PER_STOP)


def test_point_along():
    assert point_along([[0, 0], [0, 10]], 0.5) == (0, 5)
    assert point_along([[0, 0], [0, 10]], 2) == (0, 10)


@pytest.fixture()
def client():
    reset_database()
    with TestClient(app) as c:
        yield c


def auth(client, email):
    token = client.post("/auth/login", json={"email": email, "password": "demo1234"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _accepted_delivery(client):
    rest, drv = auth(client, "restaurant@demo.com"), auth(client, "driver@demo.com")
    body = {"food_type": "Rice", "meals": 50, "weight_lbs": 60, "time_sensitivity": "MEDIUM", "food_safety_confirmed": True,
            "pickup_deadline": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()}
    rescue = client.post("/rescues", json=body, headers=rest).json()
    assert rescue["match"]["eta_source"] == "ml" and len(rescue["match"]["eta_range_minutes"]) == 2
    delivery = client.post(f"/rescues/{rescue['rescue']['id']}/accept", headers=drv).json()
    return delivery, rest, drv


def test_tracking_estimates_position_then_uses_gps(client):
    delivery, rest, drv = _accepted_delivery(client)
    legs = delivery["route"]["legs"]
    assert len(legs) == 3 and all(l["eta"]["p10"] <= l["eta"]["p50"] <= l["eta"]["p90"] for l in legs)

    t = client.get(f"/deliveries/{delivery['id']}/tracking", headers=rest).json()
    assert t["target"]["kind"] == "pickup" and t["eta"]["source"] == "ml"
    assert t["driver"]["position_source"] == "estimated"

    org = auth(client, "org@demo.com")
    to_org = client.get(f"/deliveries/{delivery['id']}/tracking", headers=org).json()
    assert to_org["target"]["name"] == "Community Food Bank"
    assert to_org["eta"]["p50"] > t["eta"]["p50"]  # the org is further along the route than the pickup

    assert client.patch("/drivers/me/location", json={"lat": 25.7600, "lng": -80.3700}, headers=drv).status_code == 200
    gps = client.get(f"/deliveries/{delivery['id']}/tracking", headers=rest).json()
    assert gps["driver"]["position_source"] == "gps" and gps["driver"]["position"] == {"lat": 25.76, "lng": -80.37}

    other = auth(client, "shelter@demo.com")
    assert client.get(f"/deliveries/{delivery['id']}/tracking", headers=other).status_code == 200  # shelter is stop 2
    stranger = auth(client, "church@demo.com")
    assert client.get(f"/deliveries/{delivery['id']}/tracking", headers=stranger).status_code == 403
    assert client.patch("/drivers/me/location", json={"lat": 1, "lng": 1}, headers=rest).status_code == 403


def test_arrival_logs_a_real_leg_and_retrain_uses_only_plausible_legs(client):
    delivery, rest, drv = _accepted_delivery(client)
    with SessionLocal() as db:  # pretend the driver accepted 12 minutes ago
        d = db.get(Delivery, delivery["id"])
        d.accepted_at = d.accepted_at - timedelta(minutes=12)
        db.commit()
    client.patch(f"/deliveries/{delivery['id']}/status", json={"status": "ARRIVED_AT_RESTAURANT"}, headers=drv)
    with SessionLocal() as db:
        legs = db.query(TripLeg).all()
        assert len(legs) == 1 and 11.9 <= legs[0].actual_minutes <= 12.5 and legs[0].predicted_p50 > 0
    at = client.get(f"/deliveries/{delivery['id']}/tracking", headers=rest).json()
    assert at["note"] == "Driver is at the restaurant" and at["eta"] is None

    admin = auth(client, "admin@demo.com")
    info = client.get("/ml/eta", headers=admin).json()
    assert info["usable_real_legs"] == 1 and info["data"]["source"].startswith("OSRM")
    r = client.post("/ml/eta/retrain", headers=admin).json()
    assert r["real_trips_used"] == 1 and r["metrics"]["n_real_trips"] == 1
