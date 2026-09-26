"""Community-need (Census poverty) data and its role as one weighted matching factor."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import community_need  # noqa: E402
from app.intelligence.allocation import reweight_total, score_need  # noqa: E402

# Real seeded coordinates (app/seed.py) so these tests exercise the real, checked-in
# Census dataset rather than invented numbers.
CASA_DEMO_COCINA = (25.7630, -80.3690)
DEMO_NIGHT_SHELTER = (25.7700, -80.3550)
OUTSIDE_EVERY_TRACT = (25.0, -81.0)  # far out in the Gulf: no tract contains this point

NOW = datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)


def test_areas_are_real_census_tracts_with_attribution():
    areas = community_need.areas()
    assert len(areas) > 50
    assert community_need.source().startswith("U.S. Census Bureau, 2024 ACS 5-Year Estimates")
    for a in areas:
        assert 0.0 <= a["poverty_rate"] <= 100.0
        assert 0.0 <= a["community_need_score"] <= 1.0
        assert a["bucket"] in ("low", "moderate", "high", "very_high")
        assert a["geometry"]["type"] in ("Polygon", "MultiPolygon")


def test_bucket_thresholds_match_the_documented_cuts():
    assert community_need.community_need_score(0) == 0.0
    assert community_need.community_need_score(20) == pytest.approx(0.5)
    assert community_need.community_need_score(40) == 1.0
    assert community_need.community_need_score(80) == 1.0  # clamped, one extreme tract can't blow past 1.0


def test_score_for_a_real_seeded_organization():
    need = community_need.score_for(*DEMO_NIGHT_SHELTER)
    assert need is not None
    assert need["source"] == community_need.source()
    assert need["bucket_label"] in ("Low", "Moderate", "High", "Very High")


def test_score_for_returns_none_outside_every_tract_never_raises():
    assert community_need.score_for(*OUTSIDE_EVERY_TRACT) is None


def test_score_need_is_neutral_zero_when_no_tract_matches():
    """Missing Census data must degrade gracefully, never block or crash a match."""
    need = {"id": 1, "meals_needed": 20, "meals_fulfilled": 0, "distance_miles": 2, "lat": OUTSIDE_EVERY_TRACT[0],
           "lng": OUTSIDE_EVERY_TRACT[1]}
    score = score_need(need, meals=20, now=NOW)
    assert score["community_need_score"] == 0.0
    assert score["community_need"] is None
    assert 0.0 <= score["total"] <= 1.0


def test_score_need_components_are_bounded_and_weight_sensitive():
    lat, lng = DEMO_NIGHT_SHELTER
    need = {"id": 1, "meals_needed": 30, "meals_fulfilled": 0, "distance_miles": 3, "deadline": None, "lat": lat, "lng": lng}
    balanced = score_need(need, meals=30, now=NOW)
    for key in ("distance_score", "urgency_score", "demand_score", "capacity_score", "community_need_score", "total"):
        assert 0.0 <= balanced[key] <= 1.0

    community_first = {"distance": 0.0, "urgency": 0.0, "demand": 0.0, "capacity": 0.0, "community_need": 1.0}
    only_need = score_need(need, meals=30, now=NOW, weights=community_first)
    assert only_need["total"] == only_need["community_need_score"]


def test_community_need_never_dominates_a_close_infeasible_alternative():
    """Section 7's example: a far, very-high-need org should not automatically beat a
    close, lower-need org under the DEFAULT balanced weights -- distance still counts."""
    near_low_need = {"id": "near", "meals_needed": 40, "distance_miles": 1, "lat": 25.90, "lng": -80.20}  # outside loaded tracts -> 0 need
    far_high_need = {"id": "far", "meals_needed": 40, "distance_miles": 20, "lat": DEMO_NIGHT_SHELTER[0], "lng": DEMO_NIGHT_SHELTER[1]}
    near_score = score_need(near_low_need, meals=40, now=NOW)
    far_score = score_need(far_high_need, meals=40, now=NOW)
    assert near_score["total"] > far_score["total"]


def test_reweight_total_recomputes_from_stored_components_only():
    components = {"distance_score": 0.8, "urgency_score": 0.2, "demand_score": 0.5, "capacity_score": 0.5,
                 "community_need_score": 0.9}
    all_community = {"distance": 0.0, "urgency": 0.0, "demand": 0.0, "capacity": 0.0, "community_need": 1.0}
    assert reweight_total(components, all_community) == 0.9
