from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import services
from app.auth import driver_of, get_current_user, require_role, restaurant_of
from app.db import get_db
from app.models import Delivery, FoodRescue, Match, User
from app.schemas import RescueIn
from app.serializers import delivery_json, match_json, rescue_json

router = APIRouter(prefix="/rescues", tags=["rescues"])


def _get_rescue(db: Session, rescue_id: int) -> FoodRescue:
    rescue = db.get(FoodRescue, rescue_id)
    if rescue is None:
        raise HTTPException(404, "Rescue not found")
    return rescue


def rescue_detail(db: Session, rescue: FoodRescue) -> dict:
    match = (
        db.query(Match).filter(Match.rescue_id == rescue.id, Match.status.in_(("PENDING", "ACCEPTED")))
        .order_by(Match.id.desc()).first()
    )
    delivery = db.query(Delivery).filter_by(rescue_id=rescue.id).one_or_none()
    return {
        "rescue": rescue_json(rescue),
        "match": match_json(match) if match else None,
        "delivery": delivery_json(delivery) if delivery else None,
    }


@router.post("")
def create_rescue(body: RescueIn, user: User = Depends(require_role("RESTAURANT")), db: Session = Depends(get_db)):
    restaurant = restaurant_of(db, user)
    rescue = FoodRescue(
        restaurant_id=restaurant.id,
        food_type=body.food_type.strip(),
        meals=body.meals,
        weight_lbs=body.weight_lbs,
        pickup_address=(body.pickup_address or restaurant.address).strip(),
        lat=body.lat if body.lat is not None else restaurant.lat,
        lng=body.lng if body.lng is not None else restaurant.lng,
        pickup_deadline=body.pickup_deadline,
        time_sensitivity=body.time_sensitivity,
        description=body.description.strip(),
        status="OPEN",
    )
    db.add(rescue)
    db.flush()
    match = services.match_rescue(db, rescue)
    return {"rescue": rescue_json(rescue), "match": match_json(match) if match else None}


@router.get("/available")
def available(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    services.expire_stale(db)
    rescues = (
        db.query(FoodRescue).filter(FoodRescue.status.in_(("OPEN", "MATCHED")))
        .order_by(FoodRescue.pickup_deadline).all()
    )
    return [rescue_json(r) for r in rescues]


@router.get("/{rescue_id}")
def get_rescue(rescue_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rescue = _get_rescue(db, rescue_id)
    if user.role == "RESTAURANT" and rescue.restaurant_id != restaurant_of(db, user).id:
        raise HTTPException(403, "This rescue belongs to another restaurant")
    return rescue_detail(db, rescue)


@router.post("/{rescue_id}/accept")
def accept(rescue_id: int, user: User = Depends(require_role("DRIVER")), db: Session = Depends(get_db)):
    driver = driver_of(db, user)
    if services.active_delivery_for_driver(db, driver.id):
        raise HTTPException(409, "Finish your current delivery first")
    delivery = services.accept(db, _get_rescue(db, rescue_id), driver)
    return delivery_json(delivery)


@router.post("/{rescue_id}/decline")
def decline(rescue_id: int, user: User = Depends(require_role("DRIVER")), db: Session = Depends(get_db)):
    rescue = _get_rescue(db, rescue_id)
    match = services.decline(db, rescue, driver_of(db, user))
    return {"rescue": rescue_json(rescue), "match": match_json(match) if match else None}
