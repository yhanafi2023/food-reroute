"""Read-only aggregate views with no existing endpoint: the public impact page and
the admin network/command-center view. Everything here composes tables that
other modules already write (ImpactEvent, Organization, VolunteerProfile, Rescue,
Trip) -- no new writes, no changes to dispatch/eligibility/lifecycle.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import clock, community_need
from app.auth import ADMIN
from app.db import get_db
from app.intake import available_at, is_complete
from app.intelligence import compute_impact
from app.models import Organization, Rescue, Trip, User, VolunteerProfile
from app.views import rescue_json, trip_json

router = APIRouter(tags=["dashboards"])

ACTIVE_RESCUE_STATUSES = ("posted", "matched", "en_route_pickup", "picked_up", "en_route_dropoff")
ACTIVE_TRIP_STATUSES = ("matched", "en_route_pickup", "picked_up", "en_route_dropoff")


@router.get("/impact")
def impact(include_demo: bool = True, db: Session = Depends(get_db)):
    """Public: meals rescued, lbs diverted, deliveries completed, and community value
    estimate. No sign-in required, same as the old public impact page."""
    return compute_impact(db, include_demo)


def _restaurant_json(o: Organization) -> dict:
    return {"id": o.id, "name": o.name, "address": o.address, "lat": o.lat, "lng": o.lng,
           "is_fictional": o.is_fictional}


def _organization_json(db: Session, o: Organization) -> dict:
    p = o.receiver_profile
    return {
        "id": o.id, "name": o.name, "address": o.address, "lat": o.lat, "lng": o.lng,
        "is_fictional": o.is_fictional, "onboarding_complete": is_complete(db, o.id),
        "typical_nightly_need": p.typical_nightly_need if p else None,
        "current_need": p.current_need if p else None,
        "community_need": community_need.score_for(o.lat, o.lng),
    }


def _volunteer_json(u: User, vp: VolunteerProfile, active_ids: set) -> dict:
    now = clock.now()
    return {
        "id": u.id, "name": u.name, "first_name": u.first_name, "vehicle": vp.vehicle_description,
        "capacity_meals": vp.capacity_meals, "lat": vp.last_lat or vp.home_lat, "lng": vp.last_lng or vp.home_lng,
        "position_is_live": vp.last_lat is not None,
        "on_active_trip": u.id in active_ids,
        "available_now": u.id not in active_ids and available_at(vp.availability or {}, now),
    }


@router.get("/admin/network")
def admin_network(user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    """Every restaurant, organization and volunteer, plus active rescues/trips, for the
    admin map and command-center view. Admin-only: this is the one role that legitimately
    sees the whole network (see app/views.py's role-based visibility notes)."""
    orgs = db.query(Organization).all()
    restaurants = [_restaurant_json(o) for o in orgs if o.kind == "restaurant"]
    organizations = [_organization_json(db, o) for o in orgs if o.kind == "receiver"]

    volunteers_q = (db.query(User, VolunteerProfile).join(VolunteerProfile, VolunteerProfile.user_id == User.id)
                    .filter(User.role == "volunteer", User.active.is_(True)).all())
    active_trip_ids = {t.volunteer_user_id for t in
                       db.query(Trip.volunteer_user_id).filter(Trip.status.in_(ACTIVE_TRIP_STATUSES)).all()
                       if t.volunteer_user_id}
    volunteers = [_volunteer_json(u, vp, active_trip_ids) for u, vp in volunteers_q]

    active_rescues = db.query(Rescue).filter(Rescue.status.in_(ACTIVE_RESCUE_STATUSES)).order_by(Rescue.id.desc()).all()
    active_trips = db.query(Trip).filter(Trip.status.in_(ACTIVE_TRIP_STATUSES)).order_by(Trip.id.desc()).all()

    return {
        "restaurants": restaurants, "organizations": organizations, "volunteers": volunteers,
        "active_rescues": [rescue_json(r, user) for r in active_rescues],
        "active_trips": [trip_json(t, user) for t in active_trips],
        "stats": {
            "open_rescues": len(active_rescues), "active_trips": len(active_trips),
            "available_volunteers": sum(1 for v in volunteers if v["available_now"]),
            "total_volunteers": len(volunteers),
        },
        "impact": compute_impact(db),
    }
