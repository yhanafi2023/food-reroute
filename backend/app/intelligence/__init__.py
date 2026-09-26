"""Dev 4: AI and optimization. Public interface used by routes and logistics."""
from app.intelligence.allocation import allocate, demand_fit
from app.intelligence.impact import compute_impact
from app.intelligence.ml.model import ensure_model, forecast_tonight, model_info, predict_surplus

__all__ = [
    "allocate",
    "demand_fit",
    "compute_impact",
    "ensure_model",
    "forecast_tonight",
    "model_info",
    "predict_surplus",
]
