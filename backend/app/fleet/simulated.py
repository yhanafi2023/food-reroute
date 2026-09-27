"""SIMULATED autonomous vehicle and sidewalk robot providers (section 6a).

No Waymo API or robot API is used. These providers model the constraints a real
curbside fleet would have (service area, curbside handoff, point-to-point trips,
cargo limits, load windows) using configurable assumptions from
app/assumptions.py and travel times from the routing client (the ETA model trained
on open OSRM / OpenStreetMap data). Every quote and event is marked simulated=True.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Tuple

from sqlalchemy.orm import Session

from app import clients
from app.assumptions import (
    AV_CAPACITY_MEALS, AV_DISPATCH_DELAY_MIN, AV_SIM_FLEET_SIZE, ROBOT_CAPACITY_MEALS, ROBOT_MAX_MI,
    ROBOT_SIM_FLEET_SIZE, ROBOT_SPEED_MPH,
)
from app.fleet import geofence
from app.fleet.base import Cargo, Point, Quote
from app.intelligence.eta.features import haversine_miles
from app.models import Trip

AV_DEPOT: Point = (25.7610, -80.3760)      # illustrative staging point near FIU, inside the demo zone
ROBOT_HUBS = [(25.7575, -80.3745)]         # illustrative robot hub on FIU's campus edge


def totes_needed(cargo: Cargo) -> int:
    return 0  # no hot/cold/frozen distinction any more, so no insulated totes to count


class SimulatedWaymoProvider:
    mode = "waymo_sim"
    simulated = True
    label = "Simulated Waymo-style autonomous vehicle (no Waymo API)"

    def __init__(self, db: Session):
        self.db = db

    def _busy(self) -> int:
        return self.db.query(Trip).filter(Trip.mode == self.mode,
                                          Trip.status.in_(("matched", "en_route_pickup", "picked_up", "en_route_dropoff"))).count()

    def availability(self, zone: str = "", window: Tuple[datetime, datetime] = None) -> Dict[str, Any]:
        free = max(AV_SIM_FLEET_SIZE - self._busy(), 0)
        return {"mode": self.mode, "simulated": True, "zone": geofence.zone()["label"], "vehicles_free": free,
                "fleet_size": AV_SIM_FLEET_SIZE}

    def quote(self, pickup: Point, dropoff: Point, cargo: Cargo, start_at: datetime) -> Quote:
        q = Quote(False, self.mode, True)
        if not geofence.contains(*pickup):
            q.reason = "pickup is outside the illustrative service zone"
        elif not geofence.contains(*dropoff):
            q.reason = "drop off is outside the illustrative service zone"
        elif cargo.meals > AV_CAPACITY_MEALS:
            q.reason = f"{cargo.meals} meals is over the simulated vehicle capacity ({AV_CAPACITY_MEALS:g})"
        elif self.availability()["vehicles_free"] <= 0:
            q.reason = "no simulated vehicle free"
        if q.reason:
            return q
        mins, est, _ = clients.travel([(AV_DEPOT, pickup, 0), (pickup, dropoff, 0)])
        q.feasible, q.estimated, q.totes_needed = True, est, totes_needed(cargo)
        q.eta_pickup = start_at + timedelta(minutes=AV_DISPATCH_DELAY_MIN + mins[0]["p50"])
        q.eta_dropoff = q.eta_pickup + timedelta(minutes=mins[1]["p50"])
        q.extra = {"drive_minutes": round(mins[1]["p50"], 1)}
        return q

    def dispatch(self, trip: Trip) -> str:
        vehicle_id = f"SIM-AV-{trip.id:04d}"
        trip.vehicle_id, trip.handoff_state = vehicle_id, "vehicle_arriving"
        return vehicle_id

    def status(self, vehicle_id: str) -> Dict[str, Any]:
        trip = self.db.query(Trip).filter_by(vehicle_id=vehicle_id).order_by(Trip.id.desc()).first()
        return {"vehicle_id": vehicle_id, "simulated": True, "handoff_state": trip.handoff_state if trip else None,
                "trip_id": trip.id if trip else None}

    def cancel(self, trip: Trip) -> None:
        trip.handoff_state = None


class SimulatedSidewalkRobotProvider(SimulatedWaymoProvider):
    mode = "robot_sim"
    label = "Simulated sidewalk delivery robot"

    def availability(self, zone: str = "", window: Tuple[datetime, datetime] = None) -> Dict[str, Any]:
        free = max(ROBOT_SIM_FLEET_SIZE - self._busy(), 0)
        return {"mode": self.mode, "simulated": True, "vehicles_free": free, "fleet_size": ROBOT_SIM_FLEET_SIZE}

    def quote(self, pickup: Point, dropoff: Point, cargo: Cargo, start_at: datetime) -> Quote:
        q = Quote(False, self.mode, True)
        hub = min(ROBOT_HUBS, key=lambda h: haversine_miles(h[0], h[1], pickup[0], pickup[1]))
        to_pickup = haversine_miles(hub[0], hub[1], pickup[0], pickup[1]) * 1.3
        leg = haversine_miles(pickup[0], pickup[1], dropoff[0], dropoff[1]) * 1.3
        if leg > ROBOT_MAX_MI:
            q.reason = f"{leg:.1f} mi is beyond the simulated robot range ({ROBOT_MAX_MI:g} mi)"
        elif to_pickup > ROBOT_MAX_MI:
            q.reason = "no simulated robot hub within range of the restaurant"
        elif cargo.meals > ROBOT_CAPACITY_MEALS:
            q.reason = f"{cargo.meals} meals is over the simulated robot capacity ({ROBOT_CAPACITY_MEALS:g})"
        elif self.availability()["vehicles_free"] <= 0:
            q.reason = "no simulated robot free"
        if q.reason:
            return q
        q.feasible, q.totes_needed = True, totes_needed(cargo)
        q.eta_pickup = start_at + timedelta(minutes=to_pickup / ROBOT_SPEED_MPH * 60)
        q.eta_dropoff = q.eta_pickup + timedelta(minutes=leg / ROBOT_SPEED_MPH * 60)
        return q

    def dispatch(self, trip: Trip) -> str:
        vehicle_id = f"SIM-ROBOT-{trip.id:04d}"
        trip.vehicle_id, trip.handoff_state = vehicle_id, "vehicle_arriving"
        return vehicle_id
