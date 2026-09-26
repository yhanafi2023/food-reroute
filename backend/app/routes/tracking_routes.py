"""Live tracking, driver GPS sharing, and the ETA model."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import driver_of, get_current_user, organization_of, require_role, restaurant_of
from app.db import get_db
from app.intelligence.eta.model import eta_info, retrain
from app.models import Delivery, TripLeg, User, utcnow
from app.tracking import tracking

router = APIRouter(tags=["tracking"])
MIN_REAL_MINUTES, MAX_REAL_MINUTES = 2.0, 180.0  # ignore click-through test runs and stale legs


class LocationIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(default=0, ge=0, le=100000)


@router.patch("/drivers/me/location")
def share_location(body: LocationIn, user: User = Depends(require_role("DRIVER")), db: Session = Depends(get_db)):
    driver = driver_of(db, user)
    driver.lat, driver.lng = body.lat, body.lng
    driver.location_source, driver.location_updated_at = "gps", utcnow()
    db.commit()
    return {"ok": True, "updated_at": driver.location_updated_at.isoformat() + "Z"}


@router.get("/deliveries/{delivery_id}/tracking")
def delivery_tracking(delivery_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = db.get(Delivery, delivery_id)
    if d is None:
        raise HTTPException(404, "Delivery not found")
    org_id = None
    if user.role == "RESTAURANT" and d.rescue.restaurant_id != restaurant_of(db, user).id:
        raise HTTPException(403, "This delivery belongs to another restaurant")
    if user.role == "DRIVER" and d.driver_id != driver_of(db, user).id:
        raise HTTPException(403, "This delivery belongs to another driver")
    if user.role == "ORGANIZATION":
        org_id = organization_of(db, user).id
        if all(s.organization_id != org_id for s in d.match.stops):
            raise HTTPException(403, "This delivery is not coming to your organization")
    return tracking(d, user.role, org_id)


def _real_trips(db: Session):
    legs = db.query(TripLeg).filter(TripLeg.actual_minutes >= MIN_REAL_MINUTES,
                                    TripLeg.actual_minutes <= MAX_REAL_MINUTES).all()
    return [{**leg.features, "minutes": leg.actual_minutes} for leg in legs]


@router.get("/ml/eta")
def eta_model_info(user: User = Depends(require_role("ADMIN")), db: Session = Depends(get_db)):
    legs = db.query(TripLeg).all()
    usable = [l for l in legs if MIN_REAL_MINUTES <= l.actual_minutes <= MAX_REAL_MINUTES]
    errors = [abs(l.actual_minutes - l.predicted_p50) for l in usable if l.predicted_p50 is not None]
    return {
        **eta_info(),
        "logged_legs": len(legs),
        "usable_real_legs": len(usable),
        "real_leg_mae_minutes": round(sum(errors) / len(errors), 2) if errors else None,
        "real_leg_rule": f"Legs between {MIN_REAL_MINUTES:g} and {MAX_REAL_MINUTES:g} minutes are used for retraining.",
    }


@router.post("/ml/eta/retrain")
def eta_retrain(user: User = Depends(require_role("ADMIN")), db: Session = Depends(get_db)):
    trips = _real_trips(db)
    bundle = retrain(trips)
    return {"metrics": bundle["metrics"], "real_trips_used": len(trips)}
