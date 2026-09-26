"""Dev 4 tests: allocation, the ML prototype, and impact."""
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.intelligence import allocate, compute_impact, demand_fit, forecast_tonight, model_info, predict_surplus  # noqa: E402
from app.intelligence.impact import summarize_impact  # noqa: E402
from app.intelligence.ml import model as ml_model  # noqa: E402
from app.intelligence.ml.generate_data import generate  # noqa: E402
from app.intelligence.ml.train import time_split  # noqa: E402

FOOD_BANK = {"id": 1, "organization_name": "Community Food Bank", "meals_needed": 30, "meals_fulfilled": 0,
             "priority": "HIGH", "deadline": "2026-09-26T22:00:00"}
SHELTER = {"id": 2, "organization_name": "Hope Shelter", "meals_needed": 20, "meals_fulfilled": 0,
           "priority": "MEDIUM", "deadline": "2026-09-26T23:00:00"}


# ---------- allocation ----------

def test_demo_split_50_meals():
    assert allocate(50, [SHELTER, FOOD_BANK]) == [{"need_id": 1, "meals": 30}, {"need_id": 2, "meals": 20}]


def test_no_over_allocation_when_supply_is_short():
    result = allocate(40, [SHELTER, FOOD_BANK])
    assert result == [{"need_id": 1, "meals": 30}, {"need_id": 2, "meals": 10}]
    assert sum(a["meals"] for a in result) == 40


def test_never_exceeds_remaining_need():
    partly_filled = {**FOOD_BANK, "meals_fulfilled": 25}
    result = allocate(20, [partly_filled, SHELTER])
    assert result == [{"need_id": 1, "meals": 5}, {"need_id": 2, "meals": 15}]


def test_leftover_goes_to_best_need_so_food_is_not_stranded():
    result = allocate(70, [SHELTER, FOOD_BANK])
    assert result == [{"need_id": 1, "meals": 50}, {"need_id": 2, "meals": 20}]
    assert demand_fit(70, result, [SHELTER, FOOD_BANK]) == pytest.approx(50 / 70)


def test_at_most_three_stops():
    needs = [{"id": i, "meals_needed": 5, "meals_fulfilled": 0, "priority": "LOW"} for i in range(6)]
    result = allocate(30, needs)
    assert len(result) == 3
    assert sum(a["meals"] for a in result) == 30


def test_ties_break_on_deadline_then_distance():
    far = {"id": "far", "meals_needed": 10, "priority": "HIGH", "deadline": "2026-09-26T22:00:00", "distance_miles": 5}
    near = {**far, "id": "near", "distance_miles": 1}
    sooner = {**far, "id": "sooner", "deadline": "2026-09-26T21:00:00", "distance_miles": 9}
    assert [a["need_id"] for a in allocate(30, [far, near, sooner])] == ["sooner", "near", "far"]


def test_skips_fulfilled_needs_and_handles_empty_input():
    done = {**FOOD_BANK, "meals_fulfilled": 30}
    assert allocate(10, [done, SHELTER]) == [{"need_id": 2, "meals": 10}]
    assert allocate(10, []) == []
    assert allocate(0, [SHELTER]) == []


def test_accepts_objects_as_well_as_dicts():
    class Need:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    assert allocate(50, [Need(**SHELTER), Need(**FOOD_BANK)]) == [{"need_id": 1, "meals": 30}, {"need_id": 2, "meals": 20}]


# ---------- ML ----------

def test_synthetic_data_shape_and_time_split():
    df = generate()
    assert len(df) == 12 * 180 * 6
    assert df["is_synthetic"].all()
    train, test, cutoff = time_split(df)
    assert test["date"].nunique() == 30
    assert train["date"].max() < cutoff <= test["date"].min()


def test_model_trains_when_missing_and_predicts_probability(tmp_path, monkeypatch):
    monkeypatch.setenv("SURPLUS_MODEL_PATH", str(tmp_path / "model.joblib"))
    monkeypatch.setattr(ml_model, "_bundle", None)

    p = predict_surplus({"day_of_week": 5, "hour": 22, "food_category": "buffet", "seats": 200, "rain": 1})
    assert 0.0 <= p <= 1.0
    assert (tmp_path / "model.joblib").exists()

    info = model_info()
    assert info["model_name"] in ("LogisticRegression", "GradientBoostingClassifier")
    assert info["roc_auc"] > 0.75
    assert info["data"] == "prototype trained on synthetic data"

    quiet = predict_surplus({"day_of_week": 1, "hour": 18, "food_category": "sushi", "seats": 30, "hist_surplus_rate": 0.05})
    assert p > quiet


def test_forecast_tonight_sorted_and_bounded():
    restaurants = [{"name": "ABC Restaurant", "cuisine": "cuban", "seats": 90}, {"name": "Tiny Sushi", "food_category": "sushi", "seats": 30}]
    result = forecast_tonight(restaurants, when=datetime(2026, 9, 26, 20))
    assert [r["restaurant"] for r in result] == ["ABC Restaurant", "Tiny Sushi"]
    assert all(0.0 <= r["probability"] <= 1.0 for r in result)
    assert forecast_tonight([]) == []


# ---------- impact ----------

EVENTS = [
    {"delivery_id": 1, "restaurant_id": 1, "organization_id": 10, "meals": 30, "weight_lbs": 36.0, "delivery_minutes": 18, "is_demo_seed": False},
    {"delivery_id": 1, "restaurant_id": 1, "organization_id": 11, "meals": 20, "weight_lbs": 24.0, "delivery_minutes": 26, "is_demo_seed": False},
    {"delivery_id": 2, "restaurant_id": 2, "organization_id": 10, "meals": 15, "weight_lbs": 12.5, "delivery_minutes": 14, "is_demo_seed": True},
]


def test_impact_sums_correctly():
    impact = summarize_impact(EVENTS, value_per_meal=2.0)
    assert impact == {
        "meals_rescued": 65,
        "lbs_diverted": 72.5,
        "deliveries_completed": 2,
        "restaurants": 2,
        "organizations": 2,
        "avg_delivery_minutes": 20.0,  # (26 + 14) / 2, a split delivery ends at its last stop
        "community_value_estimate_usd": 130.0,
        "includes_demo_data": True,
    }


def test_compute_impact_reads_impact_events(monkeypatch):
    monkeypatch.setenv("MEAL_VALUE_USD", "2")
    engine = create_engine("sqlite://")
    with Session(engine) as db:
        db.execute(text(
            "CREATE TABLE impact_events (id INTEGER PRIMARY KEY, delivery_id INTEGER, restaurant_id INTEGER, "
            "organization_id INTEGER, meals INTEGER, weight_lbs REAL, delivery_minutes REAL, is_demo_seed BOOLEAN)"
        ))
        assert compute_impact(db)["meals_rescued"] == 0
        for e in EVENTS:
            db.execute(text(
                "INSERT INTO impact_events (delivery_id, restaurant_id, organization_id, meals, weight_lbs, delivery_minutes, is_demo_seed) "
                "VALUES (:delivery_id, :restaurant_id, :organization_id, :meals, :weight_lbs, :delivery_minutes, :is_demo_seed)"
            ), e)
        assert compute_impact(db) == summarize_impact(EVENTS, 2.0)
