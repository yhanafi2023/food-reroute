"""Live driver position and ETA to the person looking at the delivery.

Position, in order of preference:
  gps        the driver shared a location from their phone in the last 2 minutes
  estimated  no fresh GPS: the driver is placed along the real route leg they are
             on, by elapsed time over the ETA model's P50 for that leg
  status     the driver is at a known stop (restaurant or drop off)

ETA: the remaining legs from that position to the viewer's location are predicted
by the ETA model (P10 / P50 / P90), recomputed on every request.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.intelligence.eta.model import predict_legs, sum_legs
from app.models import Delivery, utcnow
from app.serializers import iso

GPS_FRESH = timedelta(minutes=2)
Point = Tuple[float, float]


def point_along(path: List[List[float]], fraction: float) -> Point:
    """Position `fraction` (0..1) of the way along a polyline, by distance."""
    if not path:
        raise ValueError("empty path")
    if len(path) == 1 or fraction <= 0:
        return (path[0][0], path[0][1])
    seg = [((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in zip(path, path[1:])]
    target = sum(seg) * min(fraction, 1.0)
    for (a, b), d in zip(zip(path, path[1:]), seg):
        if target <= d:
            f = 0 if d == 0 else target / d
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
        target -= d
    return (path[-1][0], path[-1][1])


def _entered(delivery: Delivery, status: str) -> Optional[datetime]:
    for h in reversed(delivery.status_history):
        if h["status"] == status:
            return datetime.fromisoformat(h["at"].replace("Z", "")).replace(tzinfo=None)
    return None


def _waypoints(delivery: Delivery) -> List[Dict[str, Any]]:
    r = delivery.rescue
    points = [{"kind": "pickup", "name": r.restaurant.name, "lat": r.lat, "lng": r.lng, "organization_id": None}]
    for s in delivery.match.stops:
        points.append({"kind": "dropoff", "name": s.organization.name, "lat": s.organization.lat,
                       "lng": s.organization.lng, "organization_id": s.organization_id})
    return points


def _estimated_position(delivery: Delivery, now: datetime) -> Tuple[Point, int, str]:
    """(position, index of the next waypoint, source). Waypoint 0 is the restaurant."""
    legs = delivery.route.get("legs") or []
    wps = _waypoints(delivery)
    status = delivery.status
    if status in ("ARRIVED_AT_RESTAURANT", "PICKED_UP"):
        return (wps[0]["lat"], wps[0]["lng"]), 1, "status"
    if status in ("DELIVERED", "CONFIRMED"):
        return (wps[-1]["lat"], wps[-1]["lng"]), len(wps), "status"
    if status == "HEADING_TO_RESTAURANT":
        start, first_leg, next_wp = delivery.accepted_at, 0, 0
    else:  # DELIVERING
        start, first_leg, next_wp = _entered(delivery, "DELIVERING") or now, 1, 1
    elapsed = max((now - start).total_seconds() / 60.0, 0.0)
    for i in range(first_leg, len(legs)):
        leg = legs[i]
        minutes = max(leg["eta"]["p50"], 0.5)
        if elapsed < minutes or i == len(legs) - 1:
            # stop just short of the waypoint: arrival is confirmed by the driver, not assumed
            return point_along(leg["geometry"], min(elapsed / minutes, 0.97)), i, "estimated"
        elapsed -= minutes
        next_wp = i + 1
    wp = wps[min(next_wp, len(wps) - 1)]
    return (wp["lat"], wp["lng"]), next_wp, "estimated"


def tracking(delivery: Delivery, viewer_role: str, viewer_org_id: Optional[int] = None,
             now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or utcnow()
    driver = delivery.driver
    wps = _waypoints(delivery)
    position, next_wp, source = _estimated_position(delivery, now)
    moving = delivery.status in ("HEADING_TO_RESTAURANT", "DELIVERING")
    fresh_gps = (driver.location_source == "gps" and driver.location_updated_at is not None
                 and now - driver.location_updated_at <= GPS_FRESH)
    if fresh_gps and moving:
        position, source = (driver.lat, driver.lng), "gps"

    # Whose location is "you"?
    if viewer_role == "RESTAURANT":
        target = 0
    elif viewer_role == "ORGANIZATION":
        target = next((i for i, w in enumerate(wps) if w["organization_id"] == viewer_org_id), len(wps) - 1)
    else:
        target = min(next_wp, len(wps) - 1)

    eta = None
    note = None
    if delivery.status in ("DELIVERED", "CONFIRMED"):
        note = "Delivered"
    elif target == 0 and delivery.status in ("ARRIVED_AT_RESTAURANT", "PICKED_UP"):
        note = "Driver is at the restaurant"
    elif target < next_wp:
        note = "Driver already passed this stop"
    else:
        path = [position] + [(w["lat"], w["lng"]) for w in wps[next_wp: target + 1]]
        legs = [(a, b, 0 if i == 0 else 1) for i, (a, b) in enumerate(zip(path, path[1:]))]
        if not moving:  # waiting at the restaurant: loading still to come
            legs = [(a, b, 1) for a, b, _ in legs]
        preds = predict_legs(legs) if legs else []
        if preds:
            total = sum_legs(preds)
            eta = {**{k: round(v, 1) for k, v in total.items()},
                   "arrival_at": iso(now + timedelta(minutes=total["p50"])),
                   "source": preds[0]["source"]}

    return {
        "delivery_id": delivery.id,
        "status": delivery.status,
        "driver": {
            "name": driver.name,
            "position": {"lat": round(position[0], 6), "lng": round(position[1], 6)},
            "position_source": source,
            "gps_updated_at": iso(driver.location_updated_at) if driver.location_source == "gps" else None,
        },
        "target": {k: wps[target][k] for k in ("kind", "name", "lat", "lng")},
        "eta": eta,
        "note": note,
        "computed_at": iso(now),
        "labels": {
            "gps": "Live GPS from the driver's phone",
            "estimated": "Estimated position along the route (no live GPS)",
            "status": "At a known stop",
        }[source],
    }
