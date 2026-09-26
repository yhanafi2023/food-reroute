"""Saving and checking trained model bundles (ETA and surplus).

On a read-only filesystem (Vercel functions) a freshly trained model is kept in memory
instead of crashing the request. Train at build time with `python -m scripts.build_models`
so no request has to train at all. A bundle saved by another scikit-learn version is
treated as stale: pickles from other versions can load but predict wrongly.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import joblib
import sklearn

log = logging.getLogger("foodflow.intelligence")


def save_bundle(bundle: Dict[str, Any], path: Path) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, path)
        return True
    except OSError as e:
        log.warning("Could not save model to %s (%s); using it from memory. "
                    "Train at build time: python -m scripts.build_models", path, e)
        return False


def is_current(bundle: Optional[Dict[str, Any]]) -> bool:
    return isinstance(bundle, dict) and bundle.get("sklearn_version") == sklearn.__version__
