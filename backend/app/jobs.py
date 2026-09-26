"""Scheduled checks (section 7 and friends). Run every SCHEDULER_SECONDS by app.main,
or directly in tests and simulations with a fake clock: run_jobs(db).

- simulated vehicles move: arrive at pickup / drop-off curbs on their ETA
- missed AV load window: vehicle leaves, rescue re-queues for volunteers only
- missed AV unload window: meals re-routed to the next eligible curbside org
- volunteer no-show: after the grace period past the expected pickup, re-queue
- food past safe_until before pickup: expire, notify everyone, log
- warnings: food expiring soon, carrier ~10 minutes away
- org schedule changed so a pending drop off would arrive while closed: re-route
- recurring schedules create drafts; 90-day intake confirmation reminders
- re-try matching for posted rescues; scheduled org reports
"""
from __future__ import annotations

from datetime import timedelta
from typing import Dict, List

from sqlalchemy.orm import Session

from app import audit, clock, dispatch, handoff, intake, lifecycle, notify
from app.assumptions import APPROACHING_WARNING_MIN, EXPIRY_WARNING_MIN, INTAKE_CONFIRM_DAYS, NO_SHOW_GRACE_MIN
from app.db import SessionLocal

RETRY_MIN = 2
from app.models import Organization, RecurringSchedule, Rescue, Trip, TripStop, User


def _users(db: Session, org_id: int) -> List[User]:
    return db.query(User).filter_by(organization_id=org_id, active=True).all()


def run_jobs(db: Session, reports: bool = True) -> Dict[str, int]:
    now = clock.now()
    counts = {k: 0 for k in ("vehicle_moves", "av_load_missed", "av_unload_missed", "no_shows", "expired", "warnings",
                             "reroutes", "drafts", "reminders", "rematched", "reports")}

    # expiry first: food past safe_until is closed, never re-queued
    for rescue in db.query(Rescue).filter(Rescue.status.in_(("posted", "matched", "en_route_pickup")),
                                          Rescue.is_draft.is_(False)).all():
        if now >= rescue.safe_until:
            people = _users(db, rescue.restaurant_org_id)
            for trip in lifecycle.active_trips(rescue):
                if trip.volunteer:
                    people.append(trip.volunteer)
                for s in trip.stops:
                    people.extend(_users(db, s.organization_id))
                lifecycle.end_trip(db, trip, "expired", None, reason="food passed safe_until before pickup")
            lifecycle.set_rescue_status(db, rescue, "expired", None, reason="passed safe_until before pickup",
                                        safe_until=rescue.safe_until.isoformat())
            notify.send(db, people, "expired", "Food expired before pickup",
                        f"Rescue #{rescue.id} from {rescue.restaurant.name} passed its safe-until time "
                        f"({clock.fmt_local(rescue.safe_until)}) before pickup and was closed.", dedupe=f"expired:{rescue.id}")
            counts["expired"] += 1
        elif rescue.safe_until - now <= timedelta(minutes=EXPIRY_WARNING_MIN) and rescue.status == "posted":
            if notify.send(db, _users(db, rescue.restaurant_org_id), "expiry_warning", "Food expiring soon",
                           f"Rescue #{rescue.id} is safe until {clock.fmt_local(rescue.safe_until)} and has no carrier yet.",
                           dedupe=f"expiry-warn:{rescue.id}"):
                counts["warnings"] += 1

    # simulated vehicles
    for trip in db.query(Trip).filter(Trip.mode != "volunteer", Trip.handoff_state.isnot(None)).all():
        if trip.status in lifecycle.INACTIVE_TRIP:
            continue
        stop = handoff.current_stop(trip)
        if trip.handoff_state == "vehicle_arriving" and now >= trip.eta_pickup_at:
            handoff.arrive_at_pickup(db, trip)
            counts["vehicle_moves"] += 1
        elif trip.handoff_state in ("at_pickup_curb", "loading") and trip.load_deadline and now > trip.load_deadline:
            audit.log(db, "av_load_window_missed", entity="trip", rescue_id=trip.rescue_id, trip_id=trip.id,
                      details={"simulated": True, "vehicle_id": trip.vehicle_id})
            trip.handoff_state = None
            lifecycle.end_trip(db, trip, "reassigned", None, reason="simulated vehicle left: load window missed")
            dispatch.requeue(db, trip.rescue, None, "the simulated vehicle left after the load window was missed; "
                                                    "a volunteer will take over", volunteer_only=True)
            counts["av_load_missed"] += 1
        elif trip.handoff_state == "in_transit" and stop and now >= stop.eta_at:
            handoff.arrive_at_dropoff(db, trip)
            counts["vehicle_moves"] += 1
        elif trip.handoff_state == "at_dropoff_curb" and trip.unload_deadline and now > trip.unload_deadline and stop:
            audit.log(db, "av_unload_window_missed", entity="trip", rescue_id=trip.rescue_id, trip_id=trip.id,
                      stop_id=stop.id, details={"simulated": True})
            new = dispatch.reroute_stop(db, stop, None, "the receiving staff did not unload within the window")
            trip.handoff_state = "in_transit" if new else None
            counts["av_unload_missed"] += 1

    # volunteer no-shows
    for trip in db.query(Trip).filter(Trip.mode == "volunteer", Trip.status.in_(("matched", "en_route_pickup"))).all():
        if now > trip.eta_pickup_at + timedelta(minutes=NO_SHOW_GRACE_MIN):
            vol = trip.volunteer_user_id
            audit.log(db, "volunteer_no_show", entity="trip", rescue_id=trip.rescue_id, trip_id=trip.id,
                      details={"expected_pickup": trip.eta_pickup_at.isoformat(), "grace_min": NO_SHOW_GRACE_MIN})
            lifecycle.end_trip(db, trip, "reassigned", None, reason="volunteer did not arrive")
            notify.send(db, [trip.volunteer], "reassigned", "Trip reassigned",
                        f"Rescue #{trip.rescue_id} was reassigned because you had not arrived.", dedupe=f"noshow:{trip.id}")
            dispatch.requeue(db, trip.rescue, None, "the volunteer did not arrive", exclude_volunteer=vol)
            counts["no_shows"] += 1

    # approaching warnings
    for trip in db.query(Trip).filter(Trip.status.in_(("en_route_pickup", "en_route_dropoff"))).all():
        if trip.status == "en_route_pickup" and 0 <= (trip.eta_pickup_at - now).total_seconds() / 60 <= APPROACHING_WARNING_MIN:
            if notify.send(db, _users(db, trip.rescue.restaurant_org_id), "approaching", "Carrier about 10 minutes away",
                           f"Pickup for rescue #{trip.rescue_id} around {clock.fmt_local(trip.eta_pickup_at)}.",
                           dedupe=f"approach-pickup:{trip.id}"):
                counts["warnings"] += 1
        for s in trip.stops:
            if trip.status == "en_route_dropoff" and s.status == "pending" and not s.approaching_notified and \
                    (s.eta_at - now).total_seconds() / 60 <= APPROACHING_WARNING_MIN:
                s.approaching_notified = True
                notify.send(db, _users(db, s.organization_id), "approaching", "Delivery about 10 minutes away",
                            f"{s.allocated_meals} meals arriving around {clock.fmt_local(s.eta_at)}. Your code: {s.dropoff_code}.",
                            dedupe=f"approach-stop:{s.id}")
                counts["warnings"] += 1

    # a pending drop off whose org would now be closed at arrival (schedule changed): re-route
    for s in db.query(TripStop).join(Trip, Trip.id == TripStop.trip_id).filter(
            TripStop.status == "pending", Trip.status.in_(("picked_up", "en_route_dropoff"))).all():
        ok, why = intake.receiving_check(db, s.organization.receiver_profile, max(s.eta_at, now))
        if not ok:
            dispatch.reroute_stop(db, s, None, f"{s.organization.name} is {why['text']}")
            counts["reroutes"] += 1

    # recurring drafts for today
    local_now = clock.to_local(now)
    for sch in db.query(RecurringSchedule).filter_by(active=True).all():
        if local_now.weekday() != sch.weekday or sch.last_draft_for == local_now.date():
            continue
        from app import posting
        from app.models import RescueTemplate

        tmpl = db.get(RescueTemplate, sch.template_id)
        hh, mm = map(int, sch.local_time.split(":"))
        deadline = clock.local_to_utc(local_now.replace(hour=hh, minute=mm, second=0, microsecond=0, tzinfo=None))
        if deadline <= now:
            continue
        creator = db.get(User, tmpl.created_by) or _users(db, sch.organization_id)[0]
        result = posting.create_post(db, creator, posting.body_from_template(tmpl, deadline, False), draft=True, schedule_id=sch.id)
        sch.last_draft_for = local_now.date()
        notify.send(db, _users(db, sch.organization_id), "draft_ready", "Tonight's pickup is ready to confirm",
                    f"Draft rescue #{result['rescue'].id} from '{tmpl.name}' for {sch.local_time}. Confirm it with one tap.",
                    dedupe=f"draft:{sch.id}:{local_now.date()}")
        counts["drafts"] += 1

    # 90-day intake confirmations
    for org in db.query(Organization).filter_by(kind="receiver").all():
        comp = intake.completeness(db, org.id)
        if comp["complete"] and any(q["confirmation_due"] for q in comp["questions"].values()):
            managers = [u for u in _users(db, org.id) if u.role == "org_manager"]
            if notify.send(db, managers, "intake_confirmation", "Please confirm your receiving info",
                           f"It has been {INTAKE_CONFIRM_DAYS} days. Check your hours, food rules and records settings.",
                           dedupe=f"intake:{org.id}:{now.date().isoformat()[:7]}"):
                counts["reminders"] += 1

    # retry matching (at most every RETRY_MIN per rescue)
    from sqlalchemy import func
    from app.models import MatchingExplanation
    for rescue in db.query(Rescue).filter_by(status="posted", is_draft=False).all():
        last = db.query(func.max(MatchingExplanation.computed_at)).filter_by(rescue_id=rescue.id).scalar()
        if now < rescue.safe_until and now < rescue.pickup_deadline and (last is None or now - last >= timedelta(minutes=RETRY_MIN)):
            if dispatch.run_matching(db, rescue).get("matched"):
                counts["rematched"] += 1

    if reports:
        from app import reports as report_builder
        counts["reports"] = report_builder.generate_due_reports(db)
    db.commit()
    return counts


LOCK_LEASE_MIN = 5  # longer than any run; a crashed run's lease simply expires
LOGIN_ATTEMPTS_KEEP_HOURS = 24


def _take_lock(db: Session) -> bool:
    """Take the jobs lease with one conditional UPDATE, so two instances or a duplicate cron call cannot both win."""
    from sqlalchemy.exc import IntegrityError

    from app.models import JobLock

    now = clock.now()
    if db.get(JobLock, "jobs") is None:
        try:
            with db.begin_nested():
                db.add(JobLock(name="jobs", locked_until=now))
        except IntegrityError:
            pass  # another instance created it first
        db.commit()
    taken = (db.query(JobLock).filter(JobLock.name == "jobs", JobLock.locked_until <= now)
             .update({JobLock.locked_until: now + timedelta(minutes=LOCK_LEASE_MIN)}, synchronize_session=False))
    db.commit()
    return taken == 1


def _release_lock(db: Session) -> None:
    from app.models import JobLock

    db.rollback()
    db.query(JobLock).filter(JobLock.name == "jobs").update({JobLock.locked_until: clock.now()}, synchronize_session=False)
    db.commit()


def run_jobs_exclusive(db: Session) -> Dict[str, object]:
    """run_jobs guarded by the lease (scheduler loop and /internal/jobs/run); also prunes old login attempts."""
    if not _take_lock(db):
        return {"skipped": "another run is in progress"}
    try:
        from app.models import LoginAttempt

        db.query(LoginAttempt).filter(
            LoginAttempt.at < clock.now() - timedelta(hours=LOGIN_ATTEMPTS_KEEP_HOURS)).delete(synchronize_session=False)
        return run_jobs(db)
    finally:
        _release_lock(db)


def run_jobs_now() -> Dict[str, object]:
    with SessionLocal() as db:
        return run_jobs_exclusive(db)
