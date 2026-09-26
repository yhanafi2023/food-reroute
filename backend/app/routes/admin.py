"""Admin network view, batch matching, simulation, ML, impact, demo reset."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import intelligence, services
from app.auth import require_role
from app.db import get_db
from app.models import Delivery, Driver, FoodNeed, FoodRescue, Organization, Restaurant, User
from app.routes.rescues import rescue_detail
from app.schemas import PredictIn
from app.seed import reset_database
from app.serializers import delivery_json, driver_json, match_json, need_json, organization_json, restaurant_json
from app.simulation import build_simulation

router = APIRouter(tags=["admin"])
REAL_FORECAST_MIN_DAYS = 90


@router.get("/admin/network")
def network(user: User = Depends(require_role("ADMIN")), db: Session = Depends(get_db)):
    services.expire_stale(db)
    active_rescues = (
        db.query(FoodRescue).filter(FoodRescue.status.in_(("OPEN", "MATCHED", "ACCEPTED", "PICKED_UP", "DELIVERED")))
        .order_by(FoodRescue.pickup_deadline).all()
    )
    active_deliveries = db.query(Delivery).filter(Delivery.status != "CONFIRMED").order_by(Delivery.id.desc()).all()
    drivers = db.query(Driver).all()
    return {
        "restaurants": [restaurant_json(r) for r in db.query(Restaurant).all()],
        "drivers": [driver_json(d) for d in drivers],
        "organizations": [organization_json(o) for o in db.query(Organization).all()],
        "needs": [need_json(n) for n in db.query(FoodNeed).filter_by(status="OPEN").all()],
        "rescues": [rescue_detail(db, r) for r in active_rescues],
        "deliveries": [delivery_json(d) for d in active_deliveries],
        "stats": {
            "open_rescues": sum(r.status in ("OPEN", "MATCHED") for r in active_rescues),
            "active_deliveries": len(active_deliveries),
            "available_drivers": sum(d.is_available for d in drivers),
            "open_needs": db.query(FoodNeed).filter_by(status="OPEN").count(),
        },
        "impact": intelligence.compute_impact(db),
    }


@router.post("/matching/run")
def run_matching(user: User = Depends(require_role("ADMIN")), db: Session = Depends(get_db)):
    matches = services.run_batch_matching(db)
    return {"matched": len(matches), "matches": [match_json(m) for m in matches]}


@router.post("/simulation/run")
def simulation(user: User = Depends(require_role("ADMIN"))):
    return build_simulation()


@router.post("/ml/predict")
def ml_predict(body: PredictIn, user: User = Depends(require_role("ADMIN", "RESTAURANT"))):
    return {"probability": round(intelligence.predict_surplus(body.features()), 4), "label": "Prototype model, synthetic training data"}


@router.get("/ml/forecast")
def ml_forecast(user: User = Depends(require_role("ADMIN")), db: Session = Depends(get_db)):
    """The surplus forecast needs real surplus history. The prototype model in
    intelligence/ml is trained on synthetic data, so it is not served here."""
    from app.models import SurplusLog

    logged_days = db.query(SurplusLog).count()
    return {
        "available": False,
        "forecast": [],
        "logged_days": logged_days,
        "needed_days": REAL_FORECAST_MIN_DAYS,
        "label": "Not available: needs real surplus history",
        "reason": ("The only trained surplus model uses synthetic data, so FoodFlow does not show its predictions. "
                   f"A forecast can be trained once businesses have logged at least {REAL_FORECAST_MIN_DAYS} real days "
                   "in the seven-day surplus log."),
    }


@router.get("/ml/info")
def ml_info():
    return intelligence.model_info()


@router.get("/impact")
def impact(include_demo: bool = False, db: Session = Depends(get_db)):
    """Public impact counts only real confirmed deliveries unless include_demo=true."""
    return intelligence.compute_impact(db, include_demo=include_demo)


@router.post("/demo/reset")
def demo_reset(user: User = Depends(require_role("ADMIN"))):
    reset_database()
    return {"ok": True, "message": "Demo data restored"}
