"""Workflow rules shared by the routes: matching, accept, decline, status changes, confirm."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.logistics import RESCUE_STATUS_FOR_DELIVERY, find_best_match, get_route, next_status, run_batch
from app.intelligence.eta.features import leg_features
from app.intelligence.eta.model import predict_legs
from app.models import Delivery, Driver, FoodNeed, FoodRescue, ImpactEvent, Match, MatchStop, TripLeg, utcnow
from app.serializers import iso


def expire_stale(db: Session) -> None:
    """Rescues whose pickup deadline passed before anyone accepted them become EXPIRED."""
    now = utcnow()
    stale = (
        db.query(FoodRescue)
        .filter(FoodRescue.status.in_(("OPEN", "MATCHED")), FoodRescue.pickup_deadline <= now)
        .all()
    )
    for rescue in stale:
        rescue.status = "EXPIRED"
        db.query(Match).filter_by(rescue_id=rescue.id, status="PENDING").update({"status": "SUPERSEDED"})
    if stale:
        db.commit()


def _committed_meals(db: Session) -> Dict[int, int]:
    """Meals already promised to each need by pending or active matches, not yet confirmed."""
    rows = (
        db.query(MatchStop.need_id, func.sum(MatchStop.meals))
        .join(Match, Match.id == MatchStop.match_id)
        .filter(Match.status.in_(("PENDING", "ACCEPTED")), MatchStop.confirmed_at.is_(None))
        .group_by(MatchStop.need_id)
        .all()
    )
    return {need_id: int(total) for need_id, total in rows}


def need_dicts(db: Session) -> List[Dict[str, Any]]:
    committed = _committed_meals(db)
    needs = db.query(FoodNeed).filter(FoodNeed.status == "OPEN", FoodNeed.deadline > utcnow()).all()
    return [
        {
            "id": n.id,
            "organization_id": n.organization_id,
            "organization_name": n.organization.name,
            "lat": n.organization.lat,
            "lng": n.organization.lng,
            "meals_needed": n.meals_needed,
            "meals_fulfilled": n.meals_fulfilled + committed.get(n.id, 0),
            "priority": n.priority,
            "deadline": n.deadline,
            "status": n.status,
        }
        for n in needs
    ]


def driver_dicts(db: Session) -> List[Dict[str, Any]]:
    """Available drivers who are not already holding an offer."""
    offered = {d for (d,) in db.query(Match.driver_id).filter(Match.status == "PENDING").all()}
    drivers = db.query(Driver).filter(Driver.is_available.is_(True)).all()
    return [
        {"id": d.id, "name": d.name, "lat": d.lat, "lng": d.lng, "capacity_meals": d.capacity_meals, "is_available": True}
        for d in drivers
        if d.id not in offered
    ]


def rescue_dict(r: FoodRescue) -> Dict[str, Any]:
    return {"id": r.id, "restaurant_name": r.restaurant.name, "meals": r.meals, "lat": r.lat, "lng": r.lng,
            "pickup_deadline": r.pickup_deadline}


def _save_match(db: Session, rescue: FoodRescue, result: Dict[str, Any]) -> Match:
    match = Match(
        rescue_id=rescue.id,
        driver_id=result["driver"]["id"],
        pickup_miles=result["pickup_miles"],
        dropoff_miles=result["dropoff_miles"],
        eta_minutes=result["eta_minutes"],
        eta_range_minutes=result.get("eta_range_minutes", []),
        pickup_eta_minutes=result.get("pickup_eta_minutes"),
        eta_source=result.get("eta_source", "rule"),
        score=result["score"],
        reasons=result["reasons"],
        top_candidates=result["top_candidates"],
        status="PENDING",
    )
    match.stops = [
        MatchStop(need_id=s["need_id"], organization_id=s["organization_id"], seq=i + 1, meals=s["meals"])
        for i, s in enumerate(result["stops"])
    ]
    db.add(match)
    rescue.status = "MATCHED"
    return match


def declined_driver_ids(db: Session, rescue_id: int) -> List[int]:
    return [d for (d,) in db.query(Match.driver_id).filter_by(rescue_id=rescue_id, status="DECLINED").all()]


def match_rescue(db: Session, rescue: FoodRescue) -> Optional[Match]:
    """Run matching for one rescue, excluding drivers who declined it. Commits."""
    result = find_best_match(
        rescue_dict(rescue), driver_dicts(db), need_dicts(db), exclude_driver_ids=declined_driver_ids(db, rescue.id)
    )
    match = _save_match(db, rescue, result) if result else None
    if match is None:
        rescue.status = "OPEN"
    db.commit()
    return match


def run_batch_matching(db: Session) -> List[Match]:
    expire_stale(db)
    rescues = db.query(FoodRescue).filter_by(status="OPEN").all()
    by_id = {r.id: r for r in rescues}
    declined = {r.id: set(declined_driver_ids(db, r.id)) for r in rescues}
    saved = []
    for result in run_batch([rescue_dict(r) for r in rescues], driver_dicts(db), need_dicts(db)):
        rescue = by_id[result["rescue_id"]]
        if result["driver"]["id"] in declined[rescue.id]:
            continue  # stays OPEN; that driver already said no to this rescue
        saved.append(_save_match(db, rescue, result))
    db.commit()
    return saved


def pending_match(db: Session, rescue_id: int) -> Optional[Match]:
    return db.query(Match).filter_by(rescue_id=rescue_id, status="PENDING").one_or_none()


def _log(delivery: Delivery, status: str) -> None:
    delivery.status = status
    delivery.status_history = [*delivery.status_history, {"status": status, "at": iso(utcnow())}]


def accept(db: Session, rescue: FoodRescue, driver: Driver) -> Delivery:
    match = pending_match(db, rescue.id)
    if match is None or match.driver_id != driver.id:
        raise HTTPException(409, "This rescue is not offered to you right now")
    points = [(driver.lat, driver.lng), (rescue.lat, rescue.lng)] + [(s.organization.lat, s.organization.lng) for s in match.stops]
    delivery = Delivery(
        rescue_id=rescue.id,
        match_id=match.id,
        driver_id=driver.id,
        meals=rescue.meals,
        weight_lbs=rescue.weight_lbs,
        route=build_route(points),
        status_history=[],
        accepted_at=utcnow(),
    )
    _log(delivery, "HEADING_TO_RESTAURANT")
    match.status = "ACCEPTED"
    rescue.status = "ACCEPTED"
    driver.is_available = False
    db.add(delivery)
    db.commit()
    return delivery


def decline(db: Session, rescue: FoodRescue, driver: Driver) -> Optional[Match]:
    match = pending_match(db, rescue.id)
    if match is None or match.driver_id != driver.id:
        raise HTTPException(409, "This rescue is not offered to you right now")
    match.status = "DECLINED"
    db.flush()
    return match_rescue(db, rescue)


def build_route(points) -> Dict[str, Any]:
    """Whole route for the map plus one road route and ML ETA per leg (for tracking)."""
    route = get_route(points)
    legs = [get_route([a, b]) for a, b in zip(points, points[1:])]
    real = [None if leg["source"] == "offline" else leg["distance_miles"] for leg in legs]
    etas = predict_legs([(a, b, 0 if i == 0 else 1) for i, (a, b) in enumerate(zip(points, points[1:]))], real)
    route["legs"] = [
        {"from": list(a), "to": list(b), "geometry": leg["geometry"], "distance_miles": leg["distance_miles"],
         "source": leg["source"], "eta": {k: round(e[k], 1) for k in ("p10", "p50", "p90")}, "eta_source": e["source"]}
        for (a, b), leg, e in zip(zip(points, points[1:]), legs, etas)
    ]
    route["ml_eta_minutes"] = round(sum(e["p50"] for e in etas), 1)
    return route


def _log_leg(db: Session, delivery: Delivery, index: int, started: datetime, ended: datetime) -> None:
    """Record a real leg duration for retraining the ETA model."""
    legs = delivery.route.get("legs") or []
    if index >= len(legs):
        return
    leg = legs[index]
    provider = None if leg["source"] == "offline" else leg["distance_miles"]
    db.add(TripLeg(
        delivery_id=delivery.id, leg_index=index, started_at=started, ended_at=ended,
        actual_minutes=round((ended - started).total_seconds() / 60.0, 2), predicted_p50=leg["eta"]["p50"],
        features=leg_features(tuple(leg["from"]), tuple(leg["to"]), provider),
    ))


def _entered(delivery: Delivery, status: str) -> Optional[datetime]:
    for h in reversed(delivery.status_history):
        if h["status"] == status:
            return datetime.fromisoformat(h["at"].replace("Z", ""))
    return None


def advance(db: Session, delivery: Delivery, requested: str) -> Delivery:
    if requested == "CONFIRMED":
        raise HTTPException(400, "The receiving organization confirms receipt")
    try:
        next_status(delivery.status, requested)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _log(delivery, requested)
    rescue, driver = delivery.rescue, delivery.driver
    rescue.status = RESCUE_STATUS_FOR_DELIVERY[requested]
    now = utcnow()
    if requested == "ARRIVED_AT_RESTAURANT":
        driver.lat, driver.lng = rescue.lat, rescue.lng
        driver.location_source, driver.location_updated_at = "status", now
        _log_leg(db, delivery, 0, delivery.accepted_at, now)
    elif requested == "DELIVERED":
        last = delivery.match.stops[-1].organization
        driver.lat, driver.lng = last.lat, last.lng
        driver.location_source, driver.location_updated_at = "status", now
        delivery.delivered_at = now
        started = _entered(delivery, "DELIVERING")
        if started and len(delivery.match.stops) == 1:
            _log_leg(db, delivery, 1, started, now)  # one drop off: the whole DELIVERING span is leg 1
        driver.is_available = True  # the driver's part is done; organizations confirm separately
    db.commit()
    return delivery


def confirm(db: Session, delivery: Delivery, organization_id: Optional[int]) -> Delivery:
    """Confirm receipt. An organization confirms its own stop; an admin (None) confirms all."""
    if delivery.status != "DELIVERED":
        raise HTTPException(400, "The driver has not marked this delivery as delivered yet")
    stops = [s for s in delivery.match.stops if s.confirmed_at is None]
    if organization_id is not None:
        if all(s.organization_id != organization_id for s in delivery.match.stops):
            raise HTTPException(403, "This delivery is not coming to your organization")
        stops = [s for s in stops if s.organization_id == organization_id]
        if not stops:
            raise HTTPException(400, "You already confirmed this delivery")
    now = utcnow()
    minutes = ((delivery.delivered_at or now) - delivery.accepted_at).total_seconds() / 60.0
    for stop in stops:
        stop.confirmed_at = now
        need = db.get(FoodNeed, stop.need_id)
        need.meals_fulfilled += stop.meals
        if need.meals_fulfilled >= need.meals_needed:
            need.status = "FULFILLED"
        db.add(
            ImpactEvent(
                delivery_id=delivery.id,
                restaurant_id=delivery.rescue.restaurant_id,
                organization_id=stop.organization_id,
                meals=stop.meals,
                weight_lbs=round(delivery.weight_lbs * stop.meals / max(delivery.meals, 1), 2),
                delivery_minutes=round(minutes, 1),
                is_demo_seed=delivery.is_demo_seed,
            )
        )
    if all(s.confirmed_at is not None for s in delivery.match.stops):
        _log(delivery, "CONFIRMED")
        delivery.rescue.status = "CONFIRMED"
    db.commit()
    return delivery


def active_delivery_for_driver(db: Session, driver_id: int) -> Optional[Delivery]:
    return (
        db.query(Delivery)
        .filter(Delivery.driver_id == driver_id, Delivery.status.notin_(("DELIVERED", "CONFIRMED")))
        .order_by(Delivery.id.desc())
        .first()
    )


def deliveries_for_org(db: Session, organization_id: int) -> Iterable[Delivery]:
    return (
        db.query(Delivery)
        .join(MatchStop, MatchStop.match_id == Delivery.match_id)
        .filter(MatchStop.organization_id == organization_id)
        .order_by(Delivery.id.desc())
        .all()
    )

