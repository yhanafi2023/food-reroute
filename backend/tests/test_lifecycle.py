"""Section 5 (and 3/4 as the way in): state machine, codes, quantities, receipt, audit, idempotency."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import clock
from app.db import SessionLocal, engine
from app.lifecycle import RESCUE_TRANSITIONS, TRIP_TRANSITIONS, check_trip_transition
from app.main import app
from app.models import Rescue, Trip
from app.seed import reset_database
from tests.helpers import EMAILS, signin


@pytest.fixture()
def client(fake_clock):
    reset_database(with_scenarios=False)
    with TestClient(app) as c:
        yield c


def post(client, h, **kw):
    body = {"quantity": 4, "unit": "tray", "attested": True,
            "pickup_deadline": (clock.now() + timedelta(minutes=90)).isoformat() + "Z", **kw}
    r = client.post("/rescues", json=body, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_quick_post_matches_a_volunteer_and_shows_codes_only_to_the_right_people(client):
    rest = signin(client, EMAILS["restaurant_staff"])
    out = post(client, rest)
    r = out["rescue"]
    assert r["est_meals"] == 48 and r["meals_per_unit_assumption"] == 12  # 4 trays x 12 (assumption)
    assert r["status"] == "matched" and r["pickup_code"]
    trip = r["trips"][0]
    assert trip["mode"] == "volunteer" and trip["carrier"]["first_name"] == "Marcus"
    assert trip["carrier"]["contact"] == "***-***-0150"  # masked
    assert "home_lat" not in str(r) and "305-555-0150" not in str(r)
    assert all("dropoff_code" not in s for s in trip["stops"])  # restaurant does not see org codes

    vol = signin(client, EMAILS["volunteer"])
    offers = client.get("/volunteers/me/trips", headers=vol).json()["offers"]
    assert offers[0]["id"] == trip["id"] and "pickup_code" not in str(offers)

    org = signin(client, EMAILS["org_staff"])
    shelter_view = client.get(f"/rescues/{r['id']}", headers=org).json()
    assert "pickup_code" not in shelter_view
    assert shelter_view["trips"][0]["stops"][0]["dropoff_code"]


def run_full_flow(client, idem=False):
    rest, vol, org = signin(client, EMAILS["restaurant_staff"]), signin(client, EMAILS["volunteer"]), signin(client, EMAILS["org_staff"])
    r = post(client, rest)["rescue"]
    trip = r["trips"][0]
    stop = trip["stops"][0]
    code = r["pickup_code"]
    dropoff_code = client.get(f"/rescues/{r['id']}", headers=org).json()["trips"][0]["stops"][0]["dropoff_code"]
    assert client.post(f"/trips/{trip['id']}/accept", headers=vol).status_code == 200
    assert client.post(f"/trips/{trip['id']}/pickup", json={"code": "0000" if code != "0000" else "1111", "picked_up_meals": 40}, headers=vol).status_code == 400
    extra = {"Idempotency-Key": "pickup-once"} if idem else {}
    p1 = client.post(f"/trips/{trip['id']}/pickup", json={"code": code, "picked_up_meals": 40}, headers={**vol, **extra})
    assert p1.status_code == 200 and p1.json()["status"] == "en_route_dropoff"
    if idem:
        p2 = client.post(f"/trips/{trip['id']}/pickup", json={"code": code, "picked_up_meals": 40}, headers={**vol, **extra})
        assert p2.status_code == 200 and p2.headers["Idempotent-Replayed"] == "true" and p2.json() == p1.json()
    assert client.post(f"/stops/{stop['id']}/deliver", json={"code": dropoff_code}, headers=vol).status_code == 200
    return r, trip, stop, rest, vol, org


def test_full_handoff_with_codes_quantities_receipt_and_audit(client):
    r, trip, stop, rest, vol, org = run_full_flow(client)
    form = client.get(f"/stops/{stop['id']}/receipt-form", headers=org).json()
    assert "received_by_name" in form["required_fields"] and "temperature_at_receipt" not in form["required_fields"]
    no_name = client.post(f"/stops/{stop['id']}/receipt", json={"condition": "accepted"}, headers=org)
    assert no_name.status_code == 422  # the shelter's Q3 answers require who received it
    ok = client.post(f"/stops/{stop['id']}/receipt", json={"condition": "accepted", "received_by_name": "Tomas"}, headers=org)
    assert ok.status_code == 200 and ok.json()["status"] == "received" and ok.json()["received_meals"] == 40
    final = client.get(f"/rescues/{r['id']}", headers=rest).json()
    assert final["status"] == "received"
    assert final["quantities"] == {"posted_meals": 48, "picked_up_meals": 40, "received_meals": 40}
    events = client.get(f"/rescues/{r['id']}/audit", headers=rest).json()
    actions = [e["action"] for e in events]
    for a in ("rescue_posted", "trip_matched", "trip_en_route_pickup", "pickup_code_rejected", "trip_picked_up",
              "trip_en_route_dropoff", "stop_delivered", "trip_delivered", "stop_received", "trip_received", "rescue_received"):
        assert a in actions, a
    assert all(e["actor_role"] for e in events)


def test_partial_acceptance_and_rejection_need_reasons(client):
    r, trip, stop, rest, vol, org = run_full_flow(client)
    base = {"temperature_f": 140, "received_by_name": "Tomas"}
    assert client.post(f"/stops/{stop['id']}/receipt", json={**base, "condition": "partially_accepted", "received_meals": 30}, headers=org).status_code == 422
    assert client.post(f"/stops/{stop['id']}/receipt", json={**base, "condition": "partially_accepted", "received_meals": 45,
                                                            "reject_reason": "quantity"}, headers=org).status_code == 422
    ok = client.post(f"/stops/{stop['id']}/receipt", json={**base, "condition": "partially_accepted", "received_meals": 30,
                                                          "reject_reason": "packaging", "reject_note": "two trays leaking"}, headers=org)
    assert ok.status_code == 200 and ok.json()["condition"] == "partially_accepted" and ok.json()["received_meals"] == 30


def test_illegal_transitions_return_409(client):
    rest, vol, org = signin(client, EMAILS["restaurant_staff"]), signin(client, EMAILS["volunteer"]), signin(client, EMAILS["org_staff"])
    r = post(client, rest)["rescue"]
    trip, stop = r["trips"][0], r["trips"][0]["stops"][0]
    code = client.get(f"/rescues/{r['id']}", headers=org).json()["trips"][0]["stops"][0]["dropoff_code"]
    assert client.post(f"/trips/{trip['id']}/pickup", json={"code": r["pickup_code"], "picked_up_meals": 40}, headers=vol).status_code == 409
    assert client.post(f"/stops/{stop['id']}/deliver", json={"code": code}, headers=vol).status_code == 409
    assert client.post(f"/stops/{stop['id']}/receipt", json={"condition": "accepted", "temperature_f": 140}, headers=org).status_code == 409
    client.post(f"/trips/{trip['id']}/accept", headers=vol)
    assert client.post(f"/trips/{trip['id']}/accept", headers=vol).status_code == 409
    assert client.post(f"/trips/{trip['id']}/decline", headers=vol).status_code == 409
    client.post(f"/trips/{trip['id']}/pickup", json={"code": r["pickup_code"], "picked_up_meals": 40}, headers=vol)
    assert client.post(f"/rescues/{r['id']}/cancel", json={"reason": "late"}, headers=rest).status_code == 409  # after pickup
    assert client.post(f"/trips/{trip['id']}/cancel", headers=vol).status_code == 409
    assert client.patch(f"/rescues/{r['id']}", json={"quantity": 2}, headers=rest).status_code == 409


def test_every_transition_in_the_state_machine():
    all_states = ["matched", "en_route_pickup", "picked_up", "en_route_dropoff", "delivered", "received", "rejected",
                  "cancelled", "reassigned", "expired"]
    for current in all_states:
        for requested in all_states:
            legal = requested in TRIP_TRANSITIONS.get(current, set())
            if legal:
                check_trip_transition(current, requested)
            else:
                with pytest.raises(Exception) as e:
                    check_trip_transition(current, requested)
                assert e.value.status_code == 409
    assert "received" not in RESCUE_TRANSITIONS  # a received rescue is final


def test_idempotent_retry_does_not_double_apply(client):
    r, trip, stop, *_ = run_full_flow(client, idem=True)
    with SessionLocal() as db:
        events = db.execute(text("SELECT count(*) FROM audit_events WHERE trip_id=:t AND action='trip_picked_up'"),
                            {"t": trip["id"]}).scalar()
        assert events == 1


def test_idempotency_key_reuse_for_another_request_is_rejected(client):
    rest = signin(client, EMAILS["restaurant_staff"])
    h = {**rest, "Idempotency-Key": "k1"}
    body = {"quantity": 2, "unit": "bag", "attested": True,
            "pickup_deadline": (clock.now() + timedelta(hours=3)).isoformat() + "Z"}
    first = client.post("/rescues", json=body, headers=h)
    again = client.post("/rescues", json=body, headers=h)
    assert again.json()["rescue"]["id"] == first.json()["rescue"]["id"]
    assert client.post("/rescues/repeat-last", json={"attested": True}, headers=h).status_code == 422


def test_audit_log_is_append_only(client):
    rest = signin(client, EMAILS["restaurant_staff"])
    post(client, rest)
    with engine.connect() as conn:
        with pytest.raises(Exception):
            conn.execute(text("UPDATE audit_events SET action='tampered'"))
        with pytest.raises(Exception):
            conn.execute(text("DELETE FROM audit_events"))


def test_restaurants_see_only_their_posts_and_others_get_404(client):
    rest = signin(client, EMAILS["restaurant_staff"])
    r = post(client, rest)["rescue"]
    other = signin(client, "manager@demo-bakery-uno.example.com")
    assert client.get(f"/rescues/{r['id']}", headers=other).status_code == 404
    assert all(x["restaurant"]["name"] == "Demo Bakery Uno" for x in client.get("/rescues", headers=other).json())
    stranger_org = signin(client, "manager@demo-food-bank.example.com")
    assert client.get(f"/rescues/{r['id']}", headers=stranger_org).status_code == 404
    other_vol = signin(client, "aisha@volunteer-demo.example.com")
    assert client.get(f"/rescues/{r['id']}", headers=other_vol).status_code == 404
    assert client.post(f"/trips/{r['trips'][0]['id']}/accept", headers=other_vol).status_code == 404
    assert client.get("/rescues", headers=other_vol).status_code == 403
