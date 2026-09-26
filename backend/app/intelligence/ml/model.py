"""Serve the surplus forecast prototype.

The model is trained on SYNTHETIC data (see generate_data.py). Every public
function here returns a real model output, never a random number, and model_info()
says plainly that the training data is synthetic.
"""
from __future__ import annotations

import threading
import warnings
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import joblib
import pandas as pd

from app.intelligence.ml.generate_data import FEATURES, HIST_PRIOR
from app.intelligence.ml.train import DATA_NOTE, model_path, train

_bundle: Optional[Dict[str, Any]] = None
_lock = threading.Lock()

DEFAULT_FEATURES: Dict[str, Any] = {
    "day_of_week": 4,
    "hour": 21,
    "food_category": "cuban",
    "seats": 80,
    "rain": 0,
    "local_event": 0,
    "hist_surplus_rate": HIST_PRIOR,
}
TONIGHT_HOUR = 21


def ensure_model() -> Dict[str, Any]:
    """Load the saved model, training it first if the file is missing or unreadable.

    Call this once on backend startup so the first /ml request is fast. Training
    takes a few seconds.
    """
    global _bundle
    if _bundle is not None:
        return _bundle
    with _lock:
        if _bundle is None:
            path = model_path()
            bundle = None
            if path.exists():
                try:
                    bundle = joblib.load(path)
                except Exception:
                    # A model saved by an incompatible scikit-learn version: retrain.
                    bundle = None
            _bundle = bundle if bundle is not None else train(path)
    return _bundle


def _clean(features: Dict[str, Any]) -> Dict[str, Any]:
    row = {**DEFAULT_FEATURES, **{k: v for k, v in (features or {}).items() if k in FEATURES and v is not None}}
    return {
        "day_of_week": int(row["day_of_week"]) % 7,
        "hour": min(max(int(row["hour"]), 18), 23),
        "food_category": str(row["food_category"]).strip().lower(),
        "seats": max(int(row["seats"]), 1),
        "rain": 1 if row["rain"] else 0,
        "local_event": 1 if row["local_event"] else 0,
        "hist_surplus_rate": min(max(float(row["hist_surplus_rate"]), 0.0), 1.0),
    }


def _predict_rows(rows: List[Dict[str, Any]]) -> List[float]:
    pipeline = ensure_model()["pipeline"]
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*encountered in matmul", category=RuntimeWarning)
        proba = pipeline.predict_proba(pd.DataFrame(rows, columns=FEATURES))[:, 1]
    return [float(min(max(p, 0.0), 1.0)) for p in proba]


def predict_surplus(features: Dict[str, Any]) -> float:
    """Probability (0 to 1) that a restaurant has at least 10 surplus meals.

    features: day_of_week, hour, food_category, seats, rain, local_event,
    hist_surplus_rate. Missing fields use DEFAULT_FEATURES, and the hour is
    clamped to the 18..23 range the model was trained on.
    """
    return _predict_rows([_clean(features)])[0]


def _get(obj: Any, *keys: str) -> Any:
    for key in keys:
        value = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
        if value is not None:
            return value
    return None


def forecast_tonight(
    restaurants: Iterable[Any],
    when: Optional[datetime] = None,
    rain: bool = False,
    local_event: bool = False,
) -> List[Dict[str, Any]]:
    """Surplus probability for each restaurant tonight, highest first.

    restaurants: dicts or ORM rows with a name and, when known, food_category
    (or cuisine), seats, and hist_surplus_rate. Tonight's day of week comes from
    `when` (default: now). The hour is the current hour during the 18..23
    service window, and 21 otherwise.
    Returns [{restaurant, probability}] with the probability rounded to 3 places.
    """
    when = when or datetime.now()
    hour = when.hour if 18 <= when.hour <= 23 else TONIGHT_HOUR
    names: List[str] = []
    rows: List[Dict[str, Any]] = []
    for r in restaurants:
        names.append(str(_get(r, "name", "restaurant_name") or "Unknown restaurant"))
        rows.append(
            _clean(
                {
                    "day_of_week": when.weekday(),
                    "hour": hour,
                    "food_category": _get(r, "food_category", "cuisine"),
                    "seats": _get(r, "seats"),
                    "rain": rain,
                    "local_event": local_event,
                    "hist_surplus_rate": _get(r, "hist_surplus_rate"),
                }
            )
        )
    if not rows:
        return []
    probs = _predict_rows(rows)
    result = [{"restaurant": n, "probability": round(p, 3)} for n, p in zip(names, probs)]
    return sorted(result, key=lambda x: x["probability"], reverse=True)


def model_info() -> Dict[str, Any]:
    """Payload for GET /ml/info."""
    bundle = ensure_model()
    metrics = bundle["metrics"]
    return {
        "model_name": bundle["model_name"],
        "roc_auc": metrics["roc_auc"],
        "roc_auc_by_model": metrics["roc_auc_by_model"],
        "accuracy": metrics["accuracy"],
        "n_train": metrics["n_train"],
        "n_test": metrics["n_test"],
        "test_period_start": metrics["test_period_start"],
        "features": bundle["features"],
        "trained_at": bundle["trained_at"],
        "data": DATA_NOTE,
        "note": "Prototype model, synthetic training data. A real deployment would train on partner restaurants' actual surplus history.",
    }
