"""Train the ETA model on REAL road-network travel times (OSRM over OpenStreetMap).

  python -m app.intelligence.eta.fetch_osrm   # refresh the data (needs internet)
  python -m app.intelligence.eta.train        # train from data/eta_osrm_miami.csv

Target: OSRM driving minutes between two real points in Miami-Dade. Handling time
at stops is added separately as a stated assumption (features.HANDLING_MINUTES_PER_STOP).
Split by batch (each batch has different sample points): batch 0 fits the range
models, batch 1 calibrates them, batch 2 tests. The P50 model trains on batches 0
and 1. Test pairs whose both ends are repeated anchor points are excluded, so the
score reflects new places.

Range: conformalized quantile regression. P10 and P90 models are fit on batch 0,
then widened by the 80th percentile of their misses on batch 1, which makes the
P10 to P90 range hold about 80% of new trips (checked on batch 2).

Compared: the old rule (straight line x 1.3 at 22 mph), Ridge regression, and
HistGradientBoosting (absolute error for P50, quantile loss for P10 and P90).
The P10 to P90 range reflects the model's error against OSRM, not traffic.
Logged real FoodFlow trips (TripLeg) are added with a higher weight on retrain.

Cost: HistGradientBoosting bins features once, then each of T trees is about
O(n x features) to build; prediction is O(T x depth) per leg.
"""
from __future__ import annotations

import json
import os
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.intelligence.artifacts import save_bundle
from app.intelligence.eta.features import FEATURES, leg_features

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
DATA_FILE = DATA_DIR / "eta_osrm_miami.csv"
META_FILE = DATA_DIR / "eta_osrm_miami.meta.json"
DEFAULT_PATH = Path(__file__).resolve().parents[1] / "ml" / "artifacts" / "eta_model.joblib"
TEST_BATCH = 2
CALIBRATION_BATCH = 1
REAL_TRIP_WEIGHT = 5.0
PROVIDER_MILES_SHARE = 0.5


def model_path() -> Path:
    return Path(os.getenv("ETA_MODEL_PATH", str(DEFAULT_PATH)))


def load_real_pairs() -> pd.DataFrame:
    raw = pd.read_csv(DATA_FILE)
    rng = np.random.default_rng(0)
    rows = [
        leg_features((r.start_lat, r.start_lng), (r.end_lat, r.end_lng),
                     r.osrm_miles if rng.random() < PROVIDER_MILES_SHARE else None)
        for r in raw.itertuples()
    ]
    df = pd.DataFrame(rows)
    df["minutes"] = raw["osrm_minutes"].to_numpy()
    df["batch"] = raw["batch"].to_numpy()
    anchors = set(zip(raw.start_lat.round(4), raw.start_lng.round(4))) & set(
        zip(raw[raw.batch == 0].start_lat.round(4), raw[raw.batch == 0].start_lng.round(4)))
    both_anchor = [((a, b) in anchors and (c, d) in anchors) for a, b, c, d in
                   zip(raw.start_lat.round(4), raw.start_lng.round(4), raw.end_lat.round(4), raw.end_lng.round(4))]
    df["repeat_pair"] = np.array(both_anchor) & (raw["batch"].to_numpy() > 0)
    return df


def _ridge_frame(df: pd.DataFrame) -> pd.DataFrame:
    x = df[FEATURES].copy()
    x["provider_miles"] = x["provider_miles"].fillna(x["est_road_miles"])
    return x


def _hgb(loss: str, quantile: Optional[float] = None) -> HistGradientBoostingRegressor:
    kw = {"quantile": quantile} if quantile is not None else {}
    return HistGradientBoostingRegressor(loss=loss, max_iter=300, learning_rate=0.08, max_leaf_nodes=31,
                                         random_state=0, **kw)


def rule_minutes(df: pd.DataFrame) -> np.ndarray:
    return df["est_road_miles"].to_numpy() / 22.0 * 60


def train(path: Path = None, real_trips: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    path = Path(path) if path is not None else model_path()
    df = load_real_pairs()
    train_df = df[df["batch"] != TEST_BATCH]
    test_df = df[(df["batch"] == TEST_BATCH) & ~df["repeat_pair"]]
    weights = np.ones(len(train_df))
    real = pd.DataFrame(real_trips or [])
    if len(real):
        train_df = pd.concat([train_df, real[FEATURES + ["minutes"]].assign(batch=0)], ignore_index=True)
        weights = np.concatenate([weights, np.full(len(real), REAL_TRIP_WEIGHT)])

    X, y = train_df[FEATURES], train_df["minutes"]
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*encountered in matmul", category=RuntimeWarning)
        ridge = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(_ridge_frame(train_df), y, ridge__sample_weight=weights)
        ridge_test = ridge.predict(_ridge_frame(test_df))
    p50 = _hgb("absolute_error").fit(X, y, sample_weight=weights)

    fit_mask = (train_df.get("batch", pd.Series(0, index=train_df.index)).fillna(0) != CALIBRATION_BATCH).to_numpy()
    calib = train_df[~fit_mask]
    p10 = _hgb("quantile", 0.1).fit(X[fit_mask], y[fit_mask], sample_weight=weights[fit_mask])
    p90 = _hgb("quantile", 0.9).fit(X[fit_mask], y[fit_mask], sample_weight=weights[fit_mask])
    miss = np.maximum(p10.predict(calib[FEATURES]) - calib["minutes"], calib["minutes"] - p90.predict(calib[FEATURES]))
    widen = float(np.quantile(miss, 0.8)) if len(miss) else 0.0

    t = test_df["minutes"].to_numpy()
    mae = {
        "rule_22mph": round(float(mean_absolute_error(t, rule_minutes(test_df))), 2),
        "ridge": round(float(mean_absolute_error(t, ridge_test)), 2),
        "hist_gradient_boosting": round(float(mean_absolute_error(t, p50.predict(test_df[FEATURES]))), 2),
    }
    raw_lo, raw_hi = p10.predict(test_df[FEATURES]), p90.predict(test_df[FEATURES])
    lo, hi = raw_lo - widen, raw_hi + widen
    best = "hist_gradient_boosting" if mae["hist_gradient_boosting"] <= mae["ridge"] else "ridge"
    meta = json.loads(META_FILE.read_text()) if META_FILE.exists() else {}
    bundle = {
        "p50": p50 if best == "hist_gradient_boosting" else ridge,
        "p50_name": best,
        "p10": p10,
        "p90": p90,
        "widen_minutes": widen,
        "features": FEATURES,
        "metrics": {
            "mae_minutes": mae,
            "chosen": best,
            "p10_p90_coverage": round(float(np.mean((t >= lo) & (t <= hi))), 3),
            "p10_p90_coverage_before_calibration": round(float(np.mean((t >= raw_lo) & (t <= raw_hi))), 3),
            "calibration_widen_minutes": round(widen, 2),
            "test_mean_minutes": round(float(t.mean()), 2),
            "n_train_pairs": int(len(train_df) - len(real)),
            "n_real_trips": int(len(real)),
            "n_test_pairs": int(len(test_df)),
        },
        "data": {
            "source": meta.get("source", "OSRM table service"),
            "map_data": meta.get("map_data", "OpenStreetMap contributors (ODbL)"),
            "fetched": meta.get("fetched"),
            "pairs": meta.get("pairs"),
            "limitations": meta.get("limitations"),
            "real_trips_used": int(len(real)),
        },
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__,
    }
    save_bundle(bundle, path)
    return bundle


if __name__ == "__main__":
    b = train()
    print(json.dumps(b["metrics"], indent=1))
