"""Regression tests for the ML model files and their pandas/scikit-learn serving path.

Deployment constraints these lock in (Vercel): the disk is read-only, so a model that cannot be
saved must still serve from memory; a saved model is loaded, never silently retrained; a file
from another scikit-learn version or a corrupt file is retrained; and the models answer the
same numbers for the same inputs (both trainings are deterministic).
"""
import logging

import joblib
import pytest

from app.intelligence import artifacts
from app.intelligence.eta import model as eta_model
from app.intelligence.eta import train as eta_train
from app.intelligence.eta.features import FEATURES as ETA_FEATURES
from app.intelligence.ml import model as surplus_model
from app.intelligence.ml import train as surplus_train
from app.intelligence.ml.generate_data import FEATURES as SURPLUS_FEATURES

# (module, env var for its file path, fresh-bundle attribute)
MODELS = [(eta_model, "ETA_MODEL_PATH", "ensure_eta_model"), (surplus_model, "SURPLUS_MODEL_PATH", "ensure_model")]
LEGS = [((25.7617, -80.3700), (25.7700, -80.3550), 0),   # short hop near FIU
        ((25.7480, -80.3500), (25.7930, -80.3500), 1),   # ~3 miles north, one handling stop before arrival
        ((25.7000, -80.4000), (25.8200, -80.3000), 0)]   # across the county
RESTAURANTS = [
    (dict(day_of_week=4, hour=21, food_category="cuban", seats=80, rain=0, local_event=0, hist_surplus_rate=0.3),
     0.5675419851748514),
    (dict(day_of_week=5, hour=22, food_category="buffet", seats=200, rain=0, local_event=1, hist_surplus_rate=0.6),
     0.9907334479393587),
    (dict(day_of_week=1, hour=19, food_category="bakery", seats=30, rain=1, local_event=0, hist_surplus_rate=0.1),
     0.05634000402353947),
]


@pytest.fixture()
def fresh(monkeypatch):
    """Forget any model already in memory (restored afterwards by monkeypatch)."""
    monkeypatch.setattr(eta_model, "_bundle", None)
    monkeypatch.setattr(surplus_model, "_bundle", None)
    monkeypatch.setattr(eta_model, "_cache", {})


def _fake_train(calls):
    def train(path=None, **_):
        calls.append(path)
        return {"sklearn_version": artifacts.sklearn.__version__, "fake": True}
    return train


@pytest.mark.parametrize("module,env,ensure", MODELS)
def test_saved_model_is_loaded_not_retrained(module, env, ensure, fresh, tmp_path, monkeypatch):
    path = tmp_path / "model.joblib"
    joblib.dump({"sklearn_version": artifacts.sklearn.__version__, "saved": True}, path)
    monkeypatch.setenv(env, str(path))
    calls = []
    monkeypatch.setattr(module, "train", _fake_train(calls))
    assert getattr(module, ensure)()["saved"] and calls == []


@pytest.mark.parametrize("module,env,ensure", MODELS)
@pytest.mark.parametrize("contents", ["other sklearn version", "corrupt file", "missing file"])
def test_stale_corrupt_or_missing_model_is_retrained(module, env, ensure, contents, fresh, tmp_path, monkeypatch):
    path = tmp_path / "model.joblib"
    if contents == "other sklearn version":
        joblib.dump({"sklearn_version": "0.0.1", "saved": True}, path)  # would load, but may predict wrongly
    elif contents == "corrupt file":
        path.write_bytes(b"not a pickle")
    monkeypatch.setenv(env, str(path))
    calls = []
    monkeypatch.setattr(module, "train", _fake_train(calls))
    assert getattr(module, ensure)()["fake"] and calls == [path]


def _read_only(*_a, **_k):
    raise PermissionError(30, "Read-only file system")


def test_read_only_disk_keeps_the_trained_model_in_memory(fresh, tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(artifacts.joblib, "dump", _read_only)
    monkeypatch.setenv("SURPLUS_MODEL_PATH", str(tmp_path / "model.joblib"))
    with caplog.at_level(logging.WARNING, logger="foodflow.intelligence"):
        p = surplus_model.predict_surplus(RESTAURANTS[0][0])  # real training, saving fails
    assert p == pytest.approx(RESTAURANTS[0][1], rel=1e-9)
    assert not (tmp_path / "model.joblib").exists()
    assert "using it from memory" in caplog.text
    assert artifacts.save_bundle({"x": 1}, tmp_path / "other.joblib") is False


def test_build_script_leaves_both_model_files(fresh, tmp_path, monkeypatch, capsys):
    from scripts import build_models

    monkeypatch.setenv("SURPLUS_MODEL_PATH", str(tmp_path / "surplus.joblib"))  # trains for real (~3 s)
    build_models.main()  # ETA: the default file, trained once per checkout
    assert (tmp_path / "surplus.joblib").exists() and eta_train.model_path().exists()
    assert "ETA model ready" in capsys.readouterr().out

    monkeypatch.setattr(surplus_model, "_bundle", None)
    monkeypatch.setenv("SURPLUS_MODEL_PATH", str(tmp_path / "unwritable" / "surplus.joblib"))
    monkeypatch.setattr(artifacts.joblib, "dump", _read_only)
    with pytest.raises(SystemExit, match="surplus model was not saved"):
        build_models.main()  # a build that cannot ship the model fails instead of deploying


def test_serving_columns_match_what_the_models_were_trained_on():
    assert list(surplus_model.ensure_model()["pipeline"].feature_names_in_) == SURPLUS_FEATURES
    bundle = eta_model.ensure_eta_model()
    for name in ("p10", "p90") + (("p50",) if bundle["p50_name"] != "ridge" else ()):
        assert list(bundle[name].feature_names_in_) == ETA_FEATURES


def test_surplus_predictions_are_unchanged():
    for features, expected in RESTAURANTS:
        assert surplus_model.predict_surplus(features) == pytest.approx(expected, rel=1e-6)
    base = RESTAURANTS[0][0]
    assert surplus_model.predict_surplus({**base, "local_event": 1}) > surplus_model.predict_surplus(base)
    assert surplus_model.predict_surplus({**base, "hist_surplus_rate": 0.8}) > surplus_model.predict_surplus(base)
    # pandas input handling: key order, extra keys and missing keys
    shuffled = dict(reversed(list(base.items())))
    assert surplus_model.predict_surplus({**shuffled, "unused": "x"}) == surplus_model.predict_surplus(base)
    assert 0.0 <= surplus_model.predict_surplus({}) <= 1.0
    ranked = surplus_model.forecast_tonight([{"name": "A", "food_category": "bakery", "seats": 30},
                                              {"name": "B", "food_category": "buffet", "seats": 200}])
    assert [r["restaurant"] for r in ranked] == ["B", "A"]


def test_eta_predictions_are_unchanged():
    expected = [(2.760067, 3.437945, 8.018051), (12.945903, 15.554415, 17.951495), (21.00355, 24.646901, 26.922013)]
    preds = eta_model.predict_legs(LEGS)
    for p, (lo, mid, hi) in zip(preds, expected):
        assert p["source"] == "ml"
        assert (p["p10"], p["p50"], p["p90"]) == pytest.approx((lo, mid, hi), abs=1e-4)
        assert p["p10"] <= p["p50"] <= p["p90"]
    assert preds[0]["p50"] < preds[1]["p50"] < preds[2]["p50"]  # farther takes longer


def test_eta_falls_back_to_the_rule_when_no_model_can_load(fresh, monkeypatch):
    def broken():
        raise RuntimeError("no model")

    monkeypatch.setattr(eta_model, "ensure_eta_model", broken)
    preds = eta_model.predict_legs(LEGS[:1])
    assert preds[0]["source"] == "rule" and preds[0]["p10"] == preds[0]["p50"] == preds[0]["p90"] > 0
