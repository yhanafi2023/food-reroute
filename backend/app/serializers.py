"""Turn rows into contract shaped JSON (snake_case, ISO times in UTC with a Z)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from app.models import Delivery, Driver, FoodNeed, FoodRescue, Match, Organization, Restaurant, User


def iso(dt: Optional[datetime]) -> Optional[str]:
    return None if dt is None else dt.replace(microsecond=0).isoformat() + "Z"


def user_json(u: User) -> Dict[str, Any]:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role}


def restaurant_json(r: Restaurant) -> Dict[str, Any]:
    return {"id": r.id, "name": r.name, "address": r.address, "lat": r.lat, "lng": r.lng,
            "food_category": r.food_category, "seats": r.seats}


def driver_json(d: Driver) -> Dict[str, Any]:
    return {"id": d.id, "name": d.name, "lat": d.lat, "lng": d.lng, "is_available": d.is_available,
            "capacity_meals": d.capacity_meals, "vehicle": d.vehicle}


def organization_json(o: Organization) -> Dict[str, Any]:
    return {"id": o.id, "name": o.name, "org_type": o.org_type, "address": o.address, "lat": o.lat, "lng": o.lng}


def rescue_json(r: FoodRescue) -> Dict[str, Any]:
    return {
        "id": r.id,
        "restaurant_id": r.restaurant_id,
        "restaurant_name": r.restaurant.name,
        "food_type": r.food_type,
        "meals": r.meals,
        "weight_lbs": r.weight_lbs,
        "pickup_address": r.pickup_address,
        "lat": r.lat,
        "lng": r.lng,
        "pickup_deadline": iso(r.pickup_deadline),
        "time_sensitivity": r.time_sensitivity,
        "description": r.description,
        "status": r.status,
        "created_at": iso(r.created_at),
    }


def need_json(n: FoodNeed) -> Dict[str, Any]:
    return {
        "id": n.id,
        "organization_id": n.organization_id,
        "organization_name": n.organization.name,
        "meals_needed": n.meals_needed,
        "meals_fulfilled": n.meals_fulfilled,
        "preferred_food": n.preferred_food,
        "deadline": iso(n.deadline),
        "priority": n.priority,
        "status": n.status,
        "lat": n.organization.lat,
        "lng": n.organization.lng,
    }


def stop_json(s) -> Dict[str, Any]:
    return {
        "need_id": s.need_id,
        "organization_id": s.organization_id,
        "name": s.organization.name,
        "lat": s.organization.lat,
        "lng": s.organization.lng,
        "meals": s.meals,
        "confirmed": s.confirmed_at is not None,
    }


def match_json(m: Match) -> Dict[str, Any]:
    return {
        "id": m.id,
        "rescue_id": m.rescue_id,
        "driver": {"id": m.driver.id, "name": m.driver.name, "lat": m.driver.lat, "lng": m.driver.lng},
        "stops": [stop_json(s) for s in m.stops],
        "pickup_miles": m.pickup_miles,
        "dropoff_miles": m.dropoff_miles,
        "eta_minutes": m.eta_minutes,
        "score": m.score,
        "reasons": m.reasons,
        "top_candidates": m.top_candidates,
        "status": m.status,
    }


def delivery_json(d: Delivery) -> Dict[str, Any]:
    r = d.rescue
    return {
        "id": d.id,
        "rescue_id": d.rescue_id,
        "match_id": d.match_id,
        "driver_id": d.driver_id,
        "driver_name": d.driver.name,
        "driver_location": {"lat": d.driver.lat, "lng": d.driver.lng},
        "status": d.status,
        "meals": d.meals,
        "weight_lbs": d.weight_lbs,
        "route": d.route,
        "restaurant": {"id": r.restaurant_id, "name": r.restaurant.name, "lat": r.lat, "lng": r.lng,
                       "address": r.pickup_address},
        "food_type": r.food_type,
        "stops": [stop_json(s) for s in d.match.stops],
        "status_history": d.status_history,
        "eta_minutes": d.route.get("eta_minutes"),
        "accepted_at": iso(d.accepted_at),
        "delivered_at": iso(d.delivered_at),
        "is_demo_seed": d.is_demo_seed,
    }
