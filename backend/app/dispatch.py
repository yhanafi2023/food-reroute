"""Intake-driven matching and mixed-fleet mode selection (sections 4 and 6).

For a posted rescue:
 1. Earliest realistic pickup: the soonest feasible carrier (volunteer, simulated AV, simulated robot).
 2. Eligibility for every receiving org within range, at the estimated arrival time, from its
    own answers (hours and cutoff, food categories, hot-food minutes, dietary and allergen rules,
    capacity and tonight's need). Every org gets a stored explanation.
 3. Allocation across eligible orgs (allocation service, with every constraint in the payload).
 4. Mode selection per leg: feasibility first (AV/robot need the service zone, curbside staff at
    both ends at the ETAs, cargo and totes), then a weighted score in minute-equivalents:
      time to arrival + margin shortfall vs safe_until + (1 - reliability) + staff handoff burden.
    A volunteer can do a multi-stop run; simulated vehicles are point to point, so a split
    allocation becomes one vehicle trip per stop. The cheaper plan wins.
 5. Trips and stops are created with pickup and drop-off codes and a plain-English mode_reason.
If no plan is feasible the rescue stays posted and the scheduler retries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import audit, clients, clock, eligibility, intake, lifecycle, notify
from app.assumptions import (
    HANDOFF_BURDEN_MIN, LOAD_WINDOW_MIN, LOADING_MIN, MATCH_RADIUS_MI, MODE_WEIGHTS, RELIABILITY_PRIOR,
    RELIABILITY_PRIOR_TRIPS, SAFE_MARGIN_TARGET_MIN,
)
from app.fleet.base import Cargo
from app.fleet.simulated import SimulatedSidewalkRobotProvider, SimulatedWaymoProvider
from app.fleet.volunteers import VolunteerProvider, describe_unavailable
from app.intelligence.eta.features import haversine_miles
from app.models import (
    MatchingExplanation, Organization, ReceiverProfile, Rescue, Trip, TripStop, User,
)

MODE_LABEL = {"volunteer": "Volunteer", "waymo_sim": "Simulated Waymo", "robot_sim": "Simulated sidewalk robot"}


@dataclass
class LegPlan:
    org: Organization
    profile: ReceiverProfile
    meals: int
    arrival: datetime


@dataclass
class TripPlan:
    mode: str
    legs: List[LegPlan]
    eta_pickup: datetime
    cost: float
    volunteer: Optional[User] = None
    totes: int = 0
    estimated: bool = False
    reason: str = ""
    route: Dict[str, Any] = field(default_factory=dict)


def reliability(db: Session, mode: str) -> float:
    """Observed completion rate for a mode, blended with the prior (an assumption) as pseudo-trips."""
    done = db.query(func.count(Trip.id)).filter(Trip.mode == mode, Trip.status.in_(("received", "rejected"))).scalar() or 0
    failed = db.query(func.count(Trip.id)).filter(Trip.mode == mode, Trip.status.in_(("reassigned", "expired"))).scalar() or 0
    prior = RELIABILITY_PRIOR[mode]
    return (done + prior * RELIABILITY_PRIOR_TRIPS) / (done + failed + RELIABILITY_PRIOR_TRIPS)


def leg_cost(db: Session, mode: str, rescue: Rescue, now: datetime, arrival: datetime) -> float:
    w = MODE_WEIGHTS
    minutes = (arrival - now).total_seconds() / 60
    margin = (rescue.safe_until - arrival).total_seconds() / 60
    return (w["time"] * minutes + w["margin"] * max(0.0, SAFE_MARGIN_TARGET_MIN - margin)
            + w["reliability"] * (1 - reliability(db, mode)) + w["handoff"] * HANDOFF_BURDEN_MIN[mode])


def _next_attempt(db: Session, rescue_id: int) -> int:
    return (db.query(func.max(MatchingExplanation.attempt)).filter_by(rescue_id=rescue_id).scalar() or 0) + 1


def _restaurant_staffed(rescue: Rescue, at: datetime) -> bool:
    prof = rescue.restaurant.restaurant_profile
    return bool(prof and intake.within_local_until(prof.staffed_until or {}, at + timedelta(minutes=LOAD_WINDOW_MIN)))


def run_matching(db: Session, rescue: Rescue, actor: Optional[User] = None) -> Dict[str, Any]:
    real_now = clock.now()
    # plan from the restaurant's chosen earliest pickup (e.g. closing), never mid-service
    now = max(real_now, rescue.pickup_not_before) if rescue.pickup_not_before else real_now
    if rescue.status != "posted" or rescue.is_draft:
        return {"matched": False, "reason": f"rescue is {rescue.status}"}
    if real_now >= rescue.safe_until or real_now >= rescue.pickup_deadline or now >= rescue.pickup_deadline:
        return {"matched": False, "reason": "past the pickup deadline or safe-until time"}
    attempt = _next_attempt(db, rescue.id)
    r_pt = (rescue.restaurant.lat, rescue.restaurant.lng)
    modes = set(rescue.allowed_modes or ["volunteer"])
    cargo = Cargo(rescue.est_meals, rescue.category, rescue.restaurant.restaurant_profile.totes_on_hand)
    vol_provider, av, robot = VolunteerProvider(db), SimulatedWaymoProvider(db), SimulatedSidewalkRobotProvider(db)

    # 1. Earliest realistic pickup across allowed modes.
    vol_cands, vol_why = ([], {})
    if "volunteer" in modes:
        vol_cands, vol_why = vol_provider.candidates(r_pt, Cargo(1, rescue.category), now, 45,
                                                     exclude=rescue.excluded_volunteer_ids or [])
    pickup_options = [now + timedelta(minutes=c["pickup_minutes"]) for c in vol_cands]
    av_note = ""
    if "waymo_sim" in modes:
        q = av.quote(r_pt, r_pt, Cargo(min(cargo.meals, 1), cargo.category, cargo.totes_available), now)
        if q.feasible and _restaurant_staffed(rescue, q.eta_pickup):
            pickup_options.append(q.eta_pickup)
        av_note = q.reason or ("" if q.feasible and _restaurant_staffed(rescue, q.eta_pickup) else "restaurant not staffed for a curbside pickup")
    earliest = min(pickup_options) if pickup_options else now + timedelta(minutes=15)

    # 2. Eligibility for every receiver in range.
    orgs = db.query(Organization).filter_by(kind="receiver").all()
    in_range = [o for o in orgs if haversine_miles(o.lat, o.lng, *r_pt) <= MATCH_RADIUS_MI]
    travel, est_travel, _ = clients.travel([(r_pt, (o.lat, o.lng), 1) for o in in_range])
    eligible: List[Dict[str, Any]] = []
    for o in orgs:
        p = o.receiver_profile
        if o not in in_range:
            reasons, cap, arrival = [{"code": "out_of_range", "text": f"more than {MATCH_RADIUS_MI:g} mi away"}], 0, None
        else:
            arrival = earliest + timedelta(minutes=LOADING_MIN + travel[in_range.index(o)]["p50"])
            reasons, cap = eligibility.check(db, p, rescue, earliest, arrival)
        db.add(MatchingExplanation(rescue_id=rescue.id, organization_id=o.id, attempt=attempt, eligible=not reasons,
                                   reasons=reasons, estimated_arrival_at=arrival, computed_at=now))
        if not reasons and cap > 0:
            eligible.append({"org": o, "profile": p, "capacity": cap, "arrival": arrival,
                             "distance": haversine_miles(o.lat, o.lng, *r_pt)})
    if not eligible:
        _log_unmatched(db, rescue, actor, "no receiving organization is eligible right now", attempt)
        return {"matched": False, "reason": "no eligible organization", "attempt": attempt}

    # 3. Allocation (constraints travel with the request).
    needs = [{"id": e["org"].id, "organization_id": e["org"].id, "meals_needed": e["capacity"], "meals_fulfilled": 0,
              "priority": "MEDIUM", "deadline": intake.receiving_until(db, e["profile"], e["arrival"]).isoformat()
              if intake.receiving_until(db, e["profile"], e["arrival"]) else None,
              "distance_miles": e["distance"],
              "constraints": {"category": rescue.category, "max_meals": e["capacity"], "curbside_ok": bool(e["profile"].curbside_ok),
                              "dietary_rules": e["profile"].dietary_rules, "refused_allergens": e["profile"].refused_allergens}}
             for e in eligible]
    allocations, est_alloc, alloc_source = clients.allocate(rescue.est_meals, needs)
    by_id = {e["org"].id: e for e in eligible}
    legs = [(by_id[a["need_id"]], a["meals"]) for a in allocations if a["meals"] > 0]

    # 4. Mode selection.
    plans = choose_plans(db, rescue, legs, modes, vol_provider, av, robot, now)
    if not plans:
        why = describe_unavailable(vol_why) if "volunteer" in modes else "volunteers not allowed for this rescue"
        _log_unmatched(db, rescue, actor, f"no carrier can make it in time: {why}; AV: {av_note or 'not feasible'}", attempt)
        return {"matched": False, "reason": "no feasible carrier", "attempt": attempt}

    # 5. Create trips.
    trips = [create_trip(db, rescue, plan, est_travel or est_alloc, vol_why, av_note, alloc_source) for plan in plans]
    lifecycle.sync_rescue(db, rescue, actor)
    audit.log(db, "matched", entity="rescue", actor=actor, rescue_id=rescue.id,
              details={"attempt": attempt, "trips": [t.id for t in trips], "allocation_source": alloc_source,
                       "estimated": est_travel or est_alloc})
    return {"matched": True, "attempt": attempt, "trips": [t.id for t in trips], "estimated": est_travel or est_alloc}


def _log_unmatched(db: Session, rescue: Rescue, actor, reason: str, attempt: int) -> None:
    audit.log(db, "match_attempt_failed", entity="rescue", actor=actor, rescue_id=rescue.id,
              details={"attempt": attempt, "reason": reason})


def _nearest_neighbor(start, legs):
    ordered, here, left = [], start, list(legs)
    while left:
        nxt = min(left, key=lambda l: haversine_miles(here[0], here[1], l[0]["org"].lat, l[0]["org"].lng))
        ordered.append(nxt)
        left.remove(nxt)
        here = (nxt[0]["org"].lat, nxt[0]["org"].lng)
    return ordered


def choose_plans(db, rescue, legs, modes, vol_provider, av, robot, now) -> List[TripPlan]:
    r_pt = (rescue.restaurant.lat, rescue.restaurant.lng)
    total = sum(m for _, m in legs)
    best_multi: Optional[TripPlan] = None

    # Option A: one volunteer for every stop.
    if "volunteer" in modes:
        ordered = _nearest_neighbor(r_pt, legs)
        pts = [r_pt] + [(e["org"].lat, e["org"].lng) for e, _ in ordered]
        seg, est, _ = clients.travel([(a, b, 0 if i == 0 else 1) for i, (a, b) in enumerate(zip(pts, pts[1:]))])
        trip_minutes = LOADING_MIN + sum(s["p50"] for s in seg)
        cands, _ = vol_provider.candidates(r_pt, Cargo(total, rescue.category), now, trip_minutes,
                                           exclude=rescue.excluded_volunteer_ids or [])
        for c in cands:
            pickup_at = now + timedelta(minutes=c["pickup_minutes"])
            t, plan_legs, ok = pickup_at + timedelta(minutes=LOADING_MIN), [], True
            for (e, meals), s in zip(ordered, seg):
                t = t + timedelta(minutes=s["p50"])
                reasons, _ = eligibility.check(db, e["profile"], rescue, pickup_at, t, "volunteer")
                if [r for r in reasons if r["code"] not in ("need_met", "capacity")]:
                    ok = False
                    break
                plan_legs.append(LegPlan(e["org"], e["profile"], meals, t))
            if ok and pickup_at <= rescue.pickup_deadline:
                cost = sum(leg_cost(db, "volunteer", rescue, now, l.arrival) for l in plan_legs)
                best_multi = TripPlan("volunteer", plan_legs, pickup_at, cost, volunteer=c["user"],
                                      estimated=est or c["estimated"])
                best_multi.route = {"miles_to_pickup": round(c["miles"], 2)}
                break

    # Option B: best single carrier per stop (vehicles are point to point).
    per_leg: List[TripPlan] = []
    used_volunteers = set()
    feasible_b = True
    for e, meals in legs:
        dest = (e["org"].lat, e["org"].lng)
        options: List[TripPlan] = []
        for provider in ([av] if "waymo_sim" in modes else []) + ([robot] if "robot_sim" in modes else []):
            q = provider.quote(r_pt, dest, Cargo(meals, rescue.category, rescue.restaurant.restaurant_profile.totes_on_hand
                                                 - sum(p.totes for p in per_leg)), now)
            if not q.feasible or q.eta_pickup > rescue.pickup_deadline or not _restaurant_staffed(rescue, q.eta_pickup):
                continue
            arrival = q.eta_dropoff + timedelta(minutes=LOADING_MIN)
            reasons, _ = eligibility.check(db, e["profile"], rescue, q.eta_pickup, arrival, provider.mode)
            if [r for r in reasons if r["code"] not in ("need_met", "capacity")]:
                continue
            options.append(TripPlan(provider.mode, [LegPlan(e["org"], e["profile"], meals, arrival)], q.eta_pickup,
                                    leg_cost(db, provider.mode, rescue, now, arrival), totes=q.totes_needed, estimated=q.estimated))
        if "volunteer" in modes:
            seg, est, _ = clients.travel([(r_pt, dest, 0)])
            cands, _ = vol_provider.candidates(r_pt, Cargo(meals, rescue.category), now, LOADING_MIN + seg[0]["p50"],
                                               exclude=list(rescue.excluded_volunteer_ids or []) + list(used_volunteers))
            for c in cands:
                pickup_at = now + timedelta(minutes=c["pickup_minutes"])
                arrival = pickup_at + timedelta(minutes=LOADING_MIN + seg[0]["p50"])
                reasons, _ = eligibility.check(db, e["profile"], rescue, pickup_at, arrival, "volunteer")
                if [r for r in reasons if r["code"] not in ("need_met", "capacity")] or pickup_at > rescue.pickup_deadline:
                    continue
                options.append(TripPlan("volunteer", [LegPlan(e["org"], e["profile"], meals, arrival)], pickup_at,
                                        leg_cost(db, "volunteer", rescue, now, arrival), volunteer=c["user"],
                                        estimated=est or c["estimated"]))
                break
        if not options:
            feasible_b = False
            break
        best = min(options, key=lambda p: (p.cost, p.mode))
        if best.volunteer:
            used_volunteers.add(best.volunteer.id)
        per_leg.append(best)

    candidates = []
    if best_multi:
        candidates.append([best_multi])
    if feasible_b and per_leg:
        candidates.append(per_leg)
    if not candidates:
        return []
    return min(candidates, key=lambda plans: (sum(p.cost for p in plans), len(plans)))


def _reason(db, rescue: Rescue, plan: TripPlan, vol_why: Dict[str, int], av_note: str, now: datetime) -> str:
    stop = plan.legs[0]
    until = intake.receiving_until(db, stop.profile, stop.arrival)
    arrival_local = clock.to_local(stop.arrival).replace(tzinfo=None)
    if until and until - arrival_local >= timedelta(hours=24):
        until_text = "open 24 hours"
    else:
        until_text = f"receiving until {until.strftime('%-I:%M %p')}" if until else "receiving"
    posted = clock.fmt_local(rescue.created_at)
    if plan.mode == "volunteer":
        v = plan.volunteer
        stops = ", ".join(f"{l.meals} meals to {l.org.name}" for l in plan.legs)
        return (f"Volunteer {v.first_name} selected: can reach the restaurant around {clock.fmt_local(plan.eta_pickup)} "
                f"with the right equipment for {rescue.category.replace('_', '-')} food; {stops}.")
    curb = "with curbside staff" if stop.profile.curbside_ok else ""
    vols = describe_unavailable(vol_why) if vol_why else "volunteers were slower"
    if "no volunteer" not in vols:
        vols = "a volunteer would arrive later or cost more"
    return (f"{MODE_LABEL[plan.mode]} selected (simulated, no real vehicle): posted {posted}, {vols}, both sites in the "
            f"illustrative service zone, {stop.org.name} {until_text} {curb}".strip() + ".")


def create_trip(db: Session, rescue: Rescue, plan: TripPlan, estimated: bool, vol_why, av_note, alloc_source) -> Trip:
    now = clock.now()
    trip = Trip(rescue=rescue, mode=plan.mode, simulated=plan.mode != "volunteer",
                volunteer_user_id=plan.volunteer.id if plan.volunteer else None, status="matched",
                mode_reason=_reason(db, rescue, plan, vol_why, av_note, now), estimated=estimated or plan.estimated,
                eta_pickup_at=plan.eta_pickup, totes_used=plan.totes, is_fictional=rescue.is_fictional, created_at=now,
                route={"allocation_source": alloc_source, **plan.route})
    db.add(trip)
    db.flush()
    for i, leg in enumerate(plan.legs, start=1):
        db.add(TripStop(trip_id=trip.id, organization_id=leg.org.id, seq=i, allocated_meals=leg.meals,
                        dropoff_code=lifecycle.code(), eta_at=leg.arrival))
    db.flush()
    db.refresh(trip)
    audit.log(db, "trip_matched", entity="trip", rescue_id=rescue.id, trip_id=trip.id, to_state="matched",
              details={"mode": plan.mode, "simulated": trip.simulated, "mode_reason": trip.mode_reason,
                       "stops": [{"organization_id": l.org.id, "meals": l.meals} for l in plan.legs]})
    if plan.totes:
        prof = rescue.restaurant.restaurant_profile
        prof.totes_on_hand -= plan.totes
        prof.totes_out += plan.totes
        from app.models import ToteLedger
        db.add(ToteLedger(organization_id=rescue.restaurant_org_id, change=-plan.totes, reason="sent_with_trip",
                          trip_id=trip.id, at=now))
    staff = _org_users(db, rescue.restaurant_org_id)
    if plan.mode == "volunteer":
        notify.send(db, [plan.volunteer], "offer", "New food rescue for you",
                    f"{rescue.est_meals} meals ({rescue.category}) from {rescue.restaurant.name}. Accept in the app.",
                    dedupe=f"offer:{trip.id}")
    else:
        provider = SimulatedWaymoProvider(db) if plan.mode == "waymo_sim" else SimulatedSidewalkRobotProvider(db)
        provider.dispatch(trip)
        lifecycle.set_trip_status(db, trip, "en_route_pickup", None, simulated=True, vehicle_id=trip.vehicle_id)
    notify.send(db, staff, "matched", "Your food has a carrier",
                f"{MODE_LABEL[plan.mode]} for rescue #{rescue.id}, pickup around {clock.fmt_local(plan.eta_pickup)}. "
                f"Pickup code: {rescue.pickup_code}.", dedupe=f"matched:{trip.id}")
    for leg in plan.legs:
        notify.send(db, _org_users(db, leg.org.id), "matched", "Food is on the way",
                    f"{leg.meals} meals ({rescue.category}) from {rescue.restaurant.name}, arriving around "
                    f"{clock.fmt_local(leg.arrival)} by {MODE_LABEL[plan.mode].lower()}.", dedupe=f"matched:{trip.id}:{leg.org.id}")
    return trip


def _org_users(db: Session, org_id: int) -> List[User]:
    return db.query(User).filter_by(organization_id=org_id, active=True).all()


def requeue(db: Session, rescue: Rescue, actor: Optional[User], reason: str, exclude_volunteer: Optional[int] = None,
            volunteer_only: bool = False) -> None:
    """Put a rescue back into matching after a no-show, decline, cancel or missed AV window."""
    if exclude_volunteer:
        rescue.excluded_volunteer_ids = sorted(set(rescue.excluded_volunteer_ids or []) | {exclude_volunteer})
    if volunteer_only:
        rescue.allowed_modes = ["volunteer"]
    rescue.requeue_count += 1
    lifecycle.sync_rescue(db, rescue, actor)
    audit.log(db, "requeued", entity="rescue", actor=actor, rescue_id=rescue.id, details={"reason": reason,
              "allowed_modes": rescue.allowed_modes, "excluded_volunteers": rescue.excluded_volunteer_ids})
    notify.send(db, _org_users(db, rescue.restaurant_org_id), "reassigned", "Finding another carrier",
                f"Rescue #{rescue.id}: {reason}. FoodFlow is finding another carrier.",
                dedupe=f"requeue:{rescue.id}:{rescue.requeue_count}")
    run_matching(db, rescue, actor)


def reroute_stop(db: Session, stop: TripStop, actor: Optional[User], reason: str) -> Optional[TripStop]:
    """The org is closed, full, or its schedule changed: send these meals to the next eligible org."""
    trip, rescue = stop.trip, stop.trip.rescue
    here = (stop.organization.lat, stop.organization.lng)
    stop.status = "rerouted"
    audit.log(db, "stop_rerouted", entity="stop", actor=actor, rescue_id=rescue.id, trip_id=trip.id, stop_id=stop.id,
              from_state="pending", to_state="rerouted", details={"reason": reason})
    now = clock.now()
    tried = {s.organization_id for s in trip.stops}
    orgs = [o for o in db.query(Organization).filter_by(kind="receiver").all() if o.id not in tried]
    travel, est, _ = clients.travel([(here, (o.lat, o.lng), 0) for o in orgs]) if orgs else ([], False, "")
    needs, arrival_by = [], {}
    for o, m in zip(orgs, travel):
        arrival = now + timedelta(minutes=m["p50"])
        reasons, cap = eligibility.check(db, o.receiver_profile, rescue, trip.started_at or now, arrival, trip.mode)
        if not reasons and cap > 0:
            needs.append({"id": o.id, "meals_needed": cap, "meals_fulfilled": 0, "priority": "MEDIUM",
                          "distance_miles": haversine_miles(o.lat, o.lng, *here)})
            arrival_by[o.id] = arrival
    allocations, est_alloc, _ = clients.allocate(stop.allocated_meals, needs)
    if not allocations:
        still_open = [s for s in trip.stops if s.status == "pending"]
        if not still_open and trip.status == "en_route_dropoff":
            if any(s.status in ("delivered", "received") for s in trip.stops):
                lifecycle.set_trip_status(db, trip, "delivered", actor)
            else:
                lifecycle.set_trip_status(db, trip, "rejected", actor, reason=f"no eligible organization after: {reason}")
        notify.send(db, _carrier_users(db, trip), "rerouted", "No other organization can take the food",
                    f"{reason}. No eligible organization is open nearby; follow the restaurant's disposal guidance.",
                    dedupe=f"reroute-none:{stop.id}")
        return None
    a = allocations[0]
    new = TripStop(trip_id=trip.id, organization_id=a["need_id"], seq=max(s.seq for s in trip.stops) + 1,
                   allocated_meals=stop.allocated_meals, dropoff_code=lifecycle.code(), eta_at=arrival_by[a["need_id"]])
    db.add(new)
    db.flush()
    trip.estimated = trip.estimated or est or est_alloc
    org = db.get(Organization, a["need_id"])
    audit.log(db, "stop_added", entity="stop", actor=actor, rescue_id=rescue.id, trip_id=trip.id, stop_id=new.id,
              to_state="pending", details={"organization_id": org.id, "meals": new.allocated_meals, "because": reason})
    notify.send(db, _carrier_users(db, trip), "rerouted", "New drop off",
                f"{reason}. Take the {new.allocated_meals} meals to {org.name} instead.", dedupe=f"reroute:{new.id}")
    notify.send(db, _org_users(db, org.id), "matched", "Food is on the way",
                f"{new.allocated_meals} meals re-routed to you, arriving around {clock.fmt_local(new.eta_at)}.",
                dedupe=f"reroute-org:{new.id}")
    return new


def _carrier_users(db: Session, trip: Trip) -> List[User]:
    if trip.volunteer_user_id:
        return [db.get(User, trip.volunteer_user_id)]
    return _org_users(db, trip.rescue.restaurant_org_id)
