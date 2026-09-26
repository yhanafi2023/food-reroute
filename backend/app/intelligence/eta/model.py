"""Serve ETA predictions (minutes) with a P10 to P90 range.

Drive time comes from the model trained on real OSRM road-network times (see
train.py). Each handling stop before arrival adds HANDLING_MINUTES_PER_STOP, a
stated assumption. If the model cannot load, the old rule is used (straight line
x 1.3 at 22 mph) and the result is marked source "rule".
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

import joblib
from threadpoolctl import threadpool_limits
import pandas as pd

from app.intelligence.eta.features import FEATURES, HANDLING_MINUTES_PER_STOP, leg_features
from app.intelligence.eta.train import _ridge_frame, model_path, train

_bundle: Optional[Dict[str, Any]] = None
_lock = threading.Lock()
MIN_MINUTES = 0.5
Point = Tuple[float, float]


def ensure_eta_model() -> Dict[str, Any]:
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
                    bundle = None
            _bundle = bundle if bundle is not None else train(path)
    return _bundle


def retrain(real_trips: List[Dict[str, Any]]) -> Dict[str, Any]:
    global _bundle
    with _lock:
        _bundle = train(model_path(), real_trips=real_trips)
        _cache.clear()
    return _bundle


_cache: Dict[tuple, Dict[str, Any]] = {}
_CACHE_MAX = 50_000


def _key(row: Dict[str, Any]) -> tuple:
    return tuple(round(row[f], 5) if isinstance(row[f], float) and row[f] == row[f] else row[f] for f in FEATURES)


def predict_drive(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drive minutes only: [{p10, p50, p90, source}] for feature rows. Repeated legs come from a cache."""
    if not rows:
        return []
    keys = [_key(r) for r in rows]
    todo = [i for i, k in enumerate(keys) if k not in _cache]
    if todo:
        for i, pred in zip(todo, _predict_uncached([rows[i] for i in todo])):
            if pred["source"] == "ml":
                if len(_cache) >= _CACHE_MAX:
                    _cache.clear()
                _cache[keys[i]] = pred
            else:
                return _predict_uncached(rows)
    return [dict(_cache[k]) for k in keys]


def _predict_uncached(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    try:
        b = ensure_eta_model()
        frame = pd.DataFrame(rows, columns=FEATURES)
        # Small batches: one thread avoids OpenMP start-up cost dominating each call.
        with threadpool_limits(limits=1):
            mid = b["p50"].predict(_ridge_frame(frame) if b["p50_name"] == "ridge" else frame)
            widen = b.get("widen_minutes", 0.0)  # conformal calibration from train.py
            lo, hi = b["p10"].predict(frame) - widen, b["p90"].predict(frame) + widen
    except Exception:
        return [dict.fromkeys(("p10", "p50", "p90"), r["est_road_miles"] / 22.0 * 60) | {"source": "rule"} for r in rows]
    out = []
    for a, m, c in zip(lo, mid, hi):
        a, m, c = sorted((max(a, MIN_MINUTES), max(m, MIN_MINUTES), max(c, MIN_MINUTES)))
        out.append({"p10": float(a), "p50": float(m), "p90": float(c), "source": "ml"})
    return out


def predict_legs(legs: Sequence[Tuple[Point, Point, int]],
                 provider_miles: Optional[Sequence[Optional[float]]] = None) -> List[Dict[str, Any]]:
    """legs: [(start, end, handling_stops_before_arrival)] -> minutes including assumed handling."""
    rows = [leg_features(s, e, None if provider_miles is None else provider_miles[i]) for i, (s, e, _) in enumerate(legs)]
    preds = predict_drive(rows)
    for p, (_, _, h) in zip(preds, legs):
        for k in ("p10", "p50", "p90"):
            p[k] += HANDLING_MINUTES_PER_STOP * h
    return preds


def sum_legs(preds: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    """Door to door over consecutive legs. Adding P10s and P90s gives a wider,
    conservative range, the safe side for pickup deadlines."""
    return {k: float(sum(p[k] for p in preds)) for k in ("p10", "p50", "p90")}


def eta_info() -> Dict[str, Any]:
    b = ensure_eta_model()
    return {
        "model": b["p50_name"],
        "metrics": b["metrics"],
        "features": b["features"],
        "trained_at": b["trained_at"],
        "data": b["data"],
        "handling_minutes_per_stop": HANDLING_MINUTES_PER_STOP,
        "assumptions": [f"{HANDLING_MINUTES_PER_STOP:g} minutes of parking and loading per stop (assumption)"],
        "note": "Trained on real OSRM road-network times for Miami-Dade (OpenStreetMap data). "
                "No live traffic until real FoodFlow trips are logged and the model is retrained.",
    }
