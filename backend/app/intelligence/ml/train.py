"""Train the surplus forecast prototype on SYNTHETIC data and save it.

  python -m app.intelligence.ml.train      (run from backend/)

Time based split: the last 30 days are the test set, so the model is always
scored on evenings that come after everything it trained on, the same way it
would be used in production. Two scikit-learn Pipelines are compared on ROC AUC
and the better one is saved with joblib, along with its metrics.

Cost: GradientBoosting training is about O(n x trees x depth) after the feature
sort, and prediction is O(trees x depth) per row. LogisticRegression is
O(n x features x iterations) to train and O(features) to predict.
"""
from __future__ import annotations

import os
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

import joblib
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.intelligence.ml.generate_data import FEATURES, FEATURES_CATEGORICAL, FEATURES_NUMERIC, LABEL, generate

TEST_DAYS = 30
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "artifacts" / "surplus_model.joblib"
DATA_NOTE = "prototype trained on synthetic data"


def model_path() -> Path:
    return Path(os.getenv("SURPLUS_MODEL_PATH", str(DEFAULT_MODEL_PATH)))


def _preprocessor() -> ColumnTransformer:
    # Day and hour are one-hot encoded because their effect is not linear
    # (Friday and Saturday are high, Sunday is in between).
    return ColumnTransformer(
        [
            ("categorical", OneHotEncoder(handle_unknown="ignore"), FEATURES_CATEGORICAL),
            ("numeric", StandardScaler(), FEATURES_NUMERIC),
        ]
    )


def candidate_models() -> Dict[str, Pipeline]:
    return {
        "LogisticRegression": Pipeline(
            [("prep", _preprocessor()), ("model", LogisticRegression(max_iter=1000))]
        ),
        "GradientBoostingClassifier": Pipeline(
            [
                ("prep", _preprocessor()),
                (
                    "model",
                    GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.1, random_state=0),
                ),
            ]
        ),
    }


def time_split(df: pd.DataFrame, test_days: int = TEST_DAYS):
    cutoff = (date.fromisoformat(df["date"].max()) - timedelta(days=test_days - 1)).isoformat()
    train = df[df["date"] < cutoff]
    test = df[df["date"] >= cutoff]
    return train, test, cutoff


def train(path: Path = None) -> Dict[str, Any]:
    """Train both candidates, keep the higher ROC AUC, save it, and return the bundle."""
    path = Path(path) if path is not None else model_path()
    df = generate()
    train_df, test_df, cutoff = time_split(df)

    scores: Dict[str, float] = {}
    fitted: Dict[str, Pipeline] = {}
    accuracy: Dict[str, float] = {}
    for name, pipeline in candidate_models().items():
        with warnings.catch_warnings():
            # numpy 2 on macOS Accelerate emits spurious matmul overflow warnings
            # during LogisticRegression fitting; the fitted coefficients are finite.
            warnings.filterwarnings("ignore", message=".*encountered in matmul", category=RuntimeWarning)
            pipeline.fit(train_df[FEATURES], train_df[LABEL])
            proba = pipeline.predict_proba(test_df[FEATURES])[:, 1]
        scores[name] = round(float(roc_auc_score(test_df[LABEL], proba)), 4)
        accuracy[name] = round(float(accuracy_score(test_df[LABEL], proba >= 0.5)), 4)
        fitted[name] = pipeline

    best = max(scores, key=scores.get)
    bundle = {
        "pipeline": fitted[best],
        "model_name": best,
        "metrics": {
            "roc_auc": scores[best],
            "accuracy": accuracy[best],
            "roc_auc_by_model": scores,
            "n_train": int(len(train_df)),
            "n_test": int(len(test_df)),
            "test_period_start": cutoff,
            "test_positive_rate": round(float(test_df[LABEL].mean()), 4),
        },
        "features": FEATURES,
        "data": DATA_NOTE,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path)
    return bundle


def main() -> None:
    bundle = train()
    m = bundle["metrics"]
    print(f"Chose {bundle['model_name']} (ROC AUC {m['roc_auc']}), compared {m['roc_auc_by_model']}")
    print(f"Train rows {m['n_train']}, test rows {m['n_test']} from {m['test_period_start']}. {DATA_NOTE}.")
    print(f"Saved to {model_path()}")


if __name__ == "__main__":
    main()
