"""Dev 3 tests: scoring, deadlines, exclusion, batch order, routing fallback, status machine."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.logistics import find_best_match, get_route, next_status, run_batch  # noqa: E402
from app.logistics import routing  # noqa: E402
from app.logistics.geo import haversine_miles, offline_eta_minutes  # noqa: E402

NOW = datetime(2026, 9, 26, 23, 0, tzinfo=timezone.utc)

ABC = {"id": 1, "restaurant_name": "ABC Restaurant", "meals": 50, "lat": 25.7635, "lng": -80.3680,
       "pickup_deadline": (NOW + timedelta(hours=3)).isoformat()}
MARCUS = {"id": 10, "name": "Marcus", "lat": 25.7580, "lng": -80.3720, "capacity_meals": 80, "is_available": True}
AISHA = {"id": 11, "name": "Aisha", "lat": 25.7450, "lng": -80.3600, "capacity_meals": 80, "is_available": True}
SAM = {"id": 12, "name": "Sam", "lat": 25.8100, "lng": -80.4200, "capacity_meals": 80, "is_available": True}
FOOD_BANK = {"id": 100, "organization_id": 20, "organization_name": "Community Food Bank", "lat": 25.7480, "lng": -80.3500,
             "meals_needed": 30, "meals_fulfilled": 0, "priority": "HIGH", "deadline": (NOW + timedelta(hours=5)).isoformat()}
SHELTER = {"id": 101, "organization_id": 21, "organization_name": "Hope Shelter", "lat": 25.7700, "lng": -80.3550,
           "meals_needed": 20, "meals_fulfilled": 0, "priority": "MEDIUM", "deadline": (NOW + timedelta(hours=5)).isoformat()}
DRIVERS = [SAM, AISHA, MARCUS]
NEEDS = [SHELTER, FOOD_BANK]


def test_geo_offline_estimate():
    # 1 degree of latitude is about 69 miles
    assert haversine_miles(25.0, -80.0, 26.0, -80.0) == pytest.approx(69.1, abs=0.2)
    assert offline_eta_minutes(22.0, 2) == pytest.approx(60 + 12)


def test_demo_match_marcus_splits_food_bank_and_shelter():
    match = find_best_match(ABC, DRIVERS, NEEDS, now=NOW)
    assert match["driver"]["name"] == "Marcus"
    assert sorted((s["name"], s["meals"]) for s in match["stops"]) == [("Community Food Bank", 30), ("Hope Shelter", 20)]
    assert 3 <= len(match["reasons"]) <= 4
    assert "closest available driver" in match["reasons"][0]
    assert 1 <= len(match["top_candidates"]) <= 3
    top = match["top_candidates"][0]
    assert top["driver_name"] == "Marcus"
    assert set(top["breakdown"]) == {"distance", "eta", "urgency", "demand_fit", "priority", "community_need"}
    assert top["score"] == pytest.approx(sum(top["breakdown"].values()), abs=0.05)
    scores = [c["score"] for c in match["top_candidates"]]
    assert scores == sorted(scores)


def test_scoring_prefers_priority_and_fit():
    match = find_best_match(ABC, DRIVERS, NEEDS, now=NOW)
    # the two stop plan places all 50 meals; a single stop plan can only place 30
    assert match["top_candidates"][0]["breakdown"]["demand_fit"] == pytest.approx(-3.0)


def test_rejects_missed_deadline():
    tight = {**ABC, "pickup_deadline": (NOW + timedelta(minutes=2)).isoformat()}
    # nobody can drive there in 2 minutes except a driver already at the door
    assert find_best_match(tight, [AISHA, SAM], NEEDS, now=NOW) is None
    past = {**ABC, "pickup_deadline": (NOW - timedelta(minutes=5)).isoformat()}
    assert find_best_match(past, DRIVERS, NEEDS, now=NOW) is None


def test_urgency_shows_in_reasons():
    soon = {**ABC, "pickup_deadline": (NOW + timedelta(minutes=25)).isoformat()}
    match = find_best_match(soon, DRIVERS, NEEDS, now=NOW)
    assert match is not None
    assert any("deadline is in 25 min" in r for r in match["reasons"])
    assert match["top_candidates"][0]["breakdown"]["urgency"] > 0


def test_excluded_driver_is_skipped():
    match = find_best_match(ABC, DRIVERS, NEEDS, exclude_driver_ids=[MARCUS["id"]], now=NOW)
    assert match["driver"]["name"] == "Aisha"


def test_unavailable_or_small_drivers_are_skipped():
    busy = {**MARCUS, "is_available": False}
    small = {**AISHA, "capacity_meals": 10}
    assert find_best_match(ABC, [busy, small, SAM], NEEDS, now=NOW)["driver"]["name"] == "Sam"
    assert find_best_match(ABC, [busy, small], NEEDS, now=NOW) is None


def test_batch_processes_earliest_deadline_first_and_tracks_needs():
    later = {**ABC, "id": 2, "meals": 20, "pickup_deadline": (NOW + timedelta(hours=2)).isoformat()}
    sooner = {**ABC, "id": 3, "meals": 20, "pickup_deadline": (NOW + timedelta(minutes=40)).isoformat()}
    matches = run_batch([later, sooner], DRIVERS, NEEDS, now=NOW)
    assert [m["rescue_id"] for m in matches] == [3, 2]
    assert matches[0]["driver"]["name"] == "Marcus"  # the urgent one gets the closest driver
    assert matches[1]["driver"]["name"] != "Marcus"  # each driver is used once
    # the second rescue cannot take food bank meals the first already filled beyond its need
    placed = {}
    for m in matches:
        for s in m["stops"]:
            placed[s["name"]] = placed.get(s["name"], 0) + s["meals"]
    assert placed.get("Community Food Bank", 0) <= 30


def test_offline_routing(monkeypatch):
    monkeypatch.setenv("ROUTING_PROVIDER", "offline")
    route = get_route([{"lat": 25.7635, "lng": -80.3680}, {"lat": 25.7480, "lng": -80.3500}, {"lat": 25.7700, "lng": -80.3550}])
    assert route["source"] == "offline"
    assert route["geometry"][0] == [25.7635, -80.3680]
    assert route["distance_miles"] > 0 and route["eta_minutes"] > 12


def test_network_failure_falls_back_to_offline(monkeypatch):
    routing.clear_cache()
    monkeypatch.setenv("ROUTING_PROVIDER", "mapbox")
    monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "test-token")

    def boom(*args, **kwargs):
        raise routing.httpx.ConnectError("offline")

    monkeypatch.setattr(routing.httpx, "get", boom)
    route = get_route([(25.76, -80.37), (25.75, -80.35)])
    assert route["source"] == "offline"


def test_mapbox_response_is_converted(monkeypatch):
    routing.clear_cache()
    monkeypatch.setenv("ROUTING_PROVIDER", "mapbox")
    monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "test-token")

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"routes": [{"geometry": {"coordinates": [[-80.37, 25.76], [-80.36, 25.755], [-80.35, 25.75]]},
                                "distance": 1609.344 * 2, "duration": 300}]}

    monkeypatch.setattr(routing.httpx, "get", lambda *a, **k: Resp())
    route = get_route([(25.76, -80.37), (25.75, -80.35)])
    assert route == {"geometry": [[25.76, -80.37], [25.755, -80.36], [25.75, -80.35]],
                     "distance_miles": 2.0, "eta_minutes": 11.0, "source": "mapbox"}
    routing.clear_cache()


def test_status_machine():
    assert next_status("HEADING_TO_RESTAURANT", "ARRIVED_AT_RESTAURANT") == "ARRIVED_AT_RESTAURANT"
    assert next_status("DELIVERED", "CONFIRMED") == "CONFIRMED"
    with pytest.raises(ValueError):
        next_status("HEADING_TO_RESTAURANT", "DELIVERED")  # skipping steps
    with pytest.raises(ValueError):
        next_status("PICKED_UP", "ARRIVED_AT_RESTAURANT")  # going back
    with pytest.raises(ValueError):
        next_status("CONFIRMED", "CONFIRMED")
    with pytest.raises(ValueError):
        next_status("PICKED_UP", "TELEPORTED")
