"""JSON views with role-based visibility.

- Restaurants: their rescue incl. the pickup code; carriers as first name, vehicle, masked contact.
- Receiving orgs: only their own drop offs, incl. their drop-off code; the same carrier view.
- Volunteers: their trips with addresses and instructions; never the codes (they must be told).
- Admin: everything.
Volunteers' full phone numbers and home locations are never returned to anyone but admins.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.auth import mask_phone, volunteer_public
from app.models import Rescue, Trip, TripStop, User


def iso(dt) -> Optional[str]:
    return None if dt is None else dt.replace(microsecond=0).isoformat() + "Z"


def carrier_json(trip: Trip, viewer: User) -> Dict[str, Any]:
    if trip.mode == "volunteer":
        v = trip.volunteer
        vp = None
        if v is not None:
            from app.models import VolunteerProfile  # local import avoids a cycle at module load
            from sqlalchemy.orm import object_session
            vp = object_session(trip).get(VolunteerProfile, v.id)
        public = volunteer_public(v, vp.vehicle_description if vp else "")
        if viewer.role == "admin" and v is not None:
            public = {**public, "user_id": v.id, "email": v.email}
        return {"type": "volunteer", "simulated": False, **(public or {})}
    return {"type": trip.mode, "simulated": True, "vehicle_id": trip.vehicle_id,
            "label": "Simulated autonomous vehicle" if trip.mode == "waymo_sim" else "Simulated sidewalk robot"}


def stop_json(stop: TripStop, viewer: User) -> Dict[str, Any]:
    org = stop.organization
    own_org = viewer.organization_id == stop.organization_id
    p = org.receiver_profile
    d = {
        "id": stop.id, "seq": stop.seq, "organization": {"id": org.id, "name": org.name, "address": org.address,
                                                          "lat": org.lat, "lng": org.lng},
        "allocated_meals": stop.allocated_meals, "status": stop.status, "eta": iso(stop.eta_at),
        "delivered_at": iso(stop.delivered_at), "received_at": iso(stop.received_at), "received_meals": stop.received_meals,
        "condition": stop.condition, "reject_reason": stop.reject_reason, "temperature_f": stop.temperature_f,
        "incomplete_fields": stop.incomplete_fields,
    }
    if viewer.role == "volunteer" or viewer.role == "admin":
        d["receiving_instructions"] = p.receiving_instructions if p else ""
        d["curb_location"] = p.curb_location if p else ""
        d["receiving_contact"] = {"name": p.receiving_contact_name, "phone": mask_phone(p.receiving_contact_phone)} if p else None
    if own_org or viewer.role == "admin":
        d["dropoff_code"] = stop.dropoff_code
        d["received_by_name"] = stop.received_by_name
        d["photo_url"] = stop.photo_url
        d["meals_served"] = stop.meals_served
    return d


def trip_json(trip: Trip, viewer: User, only_org: Optional[int] = None) -> Dict[str, Any]:
    stops = [s for s in trip.stops if only_org is None or s.organization_id == only_org]
    return {
        "id": trip.id, "rescue_id": trip.rescue_id, "mode": trip.mode, "simulated": trip.simulated,
        "status": trip.status, "handoff_state": trip.handoff_state, "mode_reason": trip.mode_reason,
        "estimated": trip.estimated, "eta_pickup": iso(trip.eta_pickup_at), "load_deadline": iso(trip.load_deadline),
        "unload_deadline": iso(trip.unload_deadline), "picked_up_meals": trip.picked_up_meals,
        "started_at": iso(trip.started_at), "finished_at": iso(trip.finished_at),
        "carrier": carrier_json(trip, viewer), "stops": [stop_json(s, viewer) for s in stops],
    }


def rescue_json(r: Rescue, viewer: User, only_org: Optional[int] = None) -> Dict[str, Any]:
    own = viewer.organization_id == r.restaurant_org_id or viewer.role == "admin"
    d = {
        "id": r.id, "status": r.status, "is_draft": r.is_draft, "is_fictional": r.is_fictional,
        "restaurant": {"id": r.restaurant.id, "name": r.restaurant.name, "address": r.restaurant.address,
                       "lat": r.restaurant.lat, "lng": r.restaurant.lng},
        "quantity": r.quantity, "unit": r.unit, "est_meals": r.est_meals,
        "meals_per_unit_assumption": r.meals_per_unit, "category": r.category, "description": r.description,
        "prepared_at": iso(r.prepared_at), "allergens": r.allergens if r.allergens_declared else None,
        "allergens_declared": r.allergens_declared, "dietary_tags": r.dietary_tags, "safe_until": iso(r.safe_until),
        "pickup_deadline": iso(r.pickup_deadline), "pickup_instructions": r.pickup_instructions,
        "attested_by": r.attested_by, "attested_at": iso(r.attested_at), "duplicate_of": r.duplicate_of,
        "created_at": iso(r.created_at), "requeue_count": r.requeue_count,
        "quantities": {"posted_meals": r.est_meals,
                       "picked_up_meals": sum(t.picked_up_meals or 0 for t in r.trips if t.picked_up_meals is not None) or None,
                       "received_meals": sum(s.received_meals or 0 for t in r.trips for s in t.stops) or None},
        "trips": [trip_json(t, viewer, only_org) for t in r.trips
                  if only_org is None or any(s.organization_id == only_org for s in t.stops)],
    }
    if own:
        d["pickup_code"] = r.pickup_code
        d["cancel_reason"] = r.cancel_reason
        from sqlalchemy.orm import object_session
        from app.models import DonationItem
        d["items"] = [{"id": i.id, "menu_item_id": i.menu_item_id, "description": i.description, "quantity": i.quantity,
                       "unit": i.unit, "estimated_meals": i.estimated_meals, "accepted_quantity": i.accepted_quantity,
                       "needs_valuation": i.needs_valuation,
                       **({"fmv_per_unit": i.fmv_per_unit, "fmv_method": i.fmv_method, "basis_per_unit": i.basis_per_unit,
                           "basis_method": i.basis_method} if viewer.role in ("restaurant_manager", "admin") else {})}
                      for i in object_session(r).query(DonationItem).filter_by(rescue_id=r.id).order_by(DonationItem.id)]
    return d
