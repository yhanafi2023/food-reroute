"""Role dashboards, organization needs, driver availability, nearby drivers."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import services
from app.auth import driver_of, organization_of, require_role, restaurant_of
from app.db import get_db
from app.logistics.geo import haversine_miles
from app.models import Delivery, Driver, FoodNeed, FoodRescue, Match, User
from app.routes.rescues import rescue_detail
from app.schemas import AvailabilityIn, NeedIn
from app.serializers import delivery_json, driver_json, match_json, need_json, organization_json, restaurant_json, rescue_json

router = APIRouter(tags=["dashboards"])

ACTIVE_RESCUE = ("OPEN", "MATCHED", "ACCEPTED", "PICKED_UP", "DELIVERED")


@router.get("/restaurants/dashboard")
def restaurant_dashboard(user: User = Depends(require_role("RESTAURANT")), db: Session = Depends(get_db)):
    services.expire_stale(db)
    restaurant = restaurant_of(db, user)
    rescues = db.query(FoodRescue).filter_by(restaurant_id=restaurant.id).order_by(FoodRescue.id.desc()).all()
    done = [r for r in rescues if r.status == "CONFIRMED"]
    return {
        "restaurant": restaurant_json(restaurant),
        "stats": {
            "active": sum(r.status in ACTIVE_RESCUE for r in rescues),
            "completed": len(done),
            "meals_donated": sum(r.meals for r in done),
            "lbs_diverted": round(sum(r.weight_lbs for r in done), 1),
        },
        "rescues": [rescue_detail(db, r) for r in rescues[:20]],
    }


@router.get("/drivers/dashboard")
def driver_dashboard(user: User = Depends(require_role("DRIVER")), db: Session = Depends(get_db)):
    services.expire_stale(db)
    driver = driver_of(db, user)
    offer = None
    pending = db.query(Match).filter_by(driver_id=driver.id, status="PENDING").first()
    if pending is not None:
        offer = {"rescue": rescue_json(db.get(FoodRescue, pending.rescue_id)), "match": match_json(pending)}
    active = services.active_delivery_for_driver(db, driver.id)
    completed = (
        db.query(Delivery).filter(Delivery.driver_id == driver.id, Delivery.status.in_(("DELIVERED", "CONFIRMED")))
        .order_by(Delivery.id.desc()).all()
    )
    return {
        "driver": driver_json(driver),
        "offer": offer,
        "active_delivery": delivery_json(active) if active else None,
        "completed": [delivery_json(d) for d in completed[:10]],
        "total_meals_moved": sum(d.meals for d in completed),
    }


@router.patch("/drivers/me/availability")
def set_availability(body: AvailabilityIn, user: User = Depends(require_role("DRIVER")), db: Session = Depends(get_db)):
    driver = driver_of(db, user)
    if not body.is_available and services.active_delivery_for_driver(db, driver.id):
        raise HTTPException(409, "Finish your current delivery before going offline")
    driver.is_available = body.is_available
    if not body.is_available:
        # hand any pending offer to the next best driver
        pending = db.query(Match).filter_by(driver_id=driver.id, status="PENDING").first()
        if pending is not None:
            pending.status = "DECLINED"
            db.flush()
            services.match_rescue(db, db.get(FoodRescue, pending.rescue_id))
    db.commit()
    return driver_json(driver)


@router.get("/drivers/nearby")
def nearby_drivers(lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180),
                   radius_miles: float = Query(default=5, gt=0, le=100),
                   user: User = Depends(require_role("RESTAURANT", "ORGANIZATION", "ADMIN")),
                   db: Session = Depends(get_db)):
    result = []
    for d in db.query(Driver).filter(Driver.is_available.is_(True)).all():
        miles = haversine_miles(lat, lng, d.lat, d.lng)
        if miles <= radius_miles:
            result.append({**driver_json(d), "distance_miles": round(miles, 2)})
    return sorted(result, key=lambda d: d["distance_miles"])


@router.post("/organizations/needs")
def create_need(body: NeedIn, user: User = Depends(require_role("ORGANIZATION")), db: Session = Depends(get_db)):
    org = organization_of(db, user)
    need = FoodNeed(organization_id=org.id, meals_needed=body.meals_needed, preferred_food=body.preferred_food,
                    deadline=body.deadline, priority=body.priority, status="OPEN")
    db.add(need)
    db.commit()
    return need_json(need)


@router.get("/organizations/needs")
def list_needs(user: User = Depends(require_role("ORGANIZATION", "ADMIN", "RESTAURANT", "DRIVER")),
               db: Session = Depends(get_db)):
    q = db.query(FoodNeed)
    if user.role == "ORGANIZATION":
        q = q.filter_by(organization_id=organization_of(db, user).id)
    else:
        q = q.filter_by(status="OPEN")
    return [need_json(n) for n in q.order_by(FoodNeed.status, FoodNeed.deadline).all()]


@router.get("/organizations/dashboard")
def organization_dashboard(user: User = Depends(require_role("ORGANIZATION")), db: Session = Depends(get_db)):
    org = organization_of(db, user)
    needs = db.query(FoodNeed).filter_by(organization_id=org.id).order_by(FoodNeed.status, FoodNeed.deadline).all()
    incoming, received = [], []
    for d in services.deliveries_for_org(db, org.id):
        mine = next(s for s in d.match.stops if s.organization_id == org.id)
        item = {"delivery": delivery_json(d), "my_meals": mine.meals, "my_stop_number": mine.seq,
                "confirmed": mine.confirmed_at is not None, "can_confirm": d.status == "DELIVERED" and mine.confirmed_at is None}
        (received if item["confirmed"] else incoming).append(item)
    return {
        "organization": organization_json(org),
        "needs": [need_json(n) for n in needs],
        "incoming": incoming,
        "received": received[:10],
        "meals_received": sum(i["my_meals"] for i in received),
    }
