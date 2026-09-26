"""Restaurant posting and rescue views (sections 3, 4, 5)."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app import audit, clock, dispatch, posting
from app.auth import RESTAURANT_ANY, RESTAURANT_MANAGER, get_current_user
from app.db import get_db
from app.eligibility import group
from app.models import MatchingExplanation, Organization, RecurringSchedule, Rescue, RescueTemplate, User
from app.schemas_common import to_naive_utc
from app.views import iso, rescue_json

router = APIRouter(tags=["rescues"])


def load_rescue(db: Session, rescue_id: int, user: User) -> tuple:
    """(rescue, only_org) if the user may see it, else 404. Orgs see only their own drop offs."""
    r = db.get(Rescue, rescue_id)
    if r is None:
        raise HTTPException(404, "Rescue not found")
    if user.role == "admin" or (user.role in ("restaurant_staff", "restaurant_manager") and user.organization_id == r.restaurant_org_id):
        return r, None
    if user.role == "volunteer" and any(t.volunteer_user_id == user.id for t in r.trips):
        return r, None
    if user.role in ("org_staff", "org_manager") and any(s.organization_id == user.organization_id for t in r.trips for s in t.stops):
        return r, user.organization_id
    raise HTTPException(404, "Rescue not found")


def _own(db: Session, rescue_id: int, user: User) -> Rescue:
    r = db.get(Rescue, rescue_id)
    if r is None or r.restaurant_org_id != user.organization_id:
        raise HTTPException(404, "Rescue not found")
    return r


def _post_and_match(db: Session, user: User, body: posting.QuickPost):
    result = posting.create_post(db, user, body)
    rescue = result["rescue"]
    match = dispatch.run_matching(db, rescue, user)
    db.commit()
    db.refresh(rescue)
    return {"rescue": rescue_json(rescue, user), "warnings": result["warnings"], "matching": match}


@router.post("/rescues")
def quick_post(body: posting.QuickPost, user: User = Depends(RESTAURANT_ANY), db: Session = Depends(get_db)):
    """Quick post: quantity + unit + category + pickup deadline + attestation. Everything else optional."""
    return _post_and_match(db, user, body)


class RepeatIn(BaseModel):
    attested: bool
    pickup_deadline: Optional[datetime] = None

    _utc = field_validator("pickup_deadline")(lambda v: to_naive_utc(v) if v else v)


def _same_time_today(previous: datetime) -> datetime:
    """The previous post's local deadline time, today (or tomorrow if that time has passed)."""
    prev_local, now_local = clock.to_local(previous), clock.to_local(clock.now())
    cand = now_local.replace(hour=prev_local.hour, minute=prev_local.minute, second=0, microsecond=0)
    if cand <= now_local:
        cand += timedelta(days=1)
    return clock.local_to_utc(cand.replace(tzinfo=None))


@router.post("/rescues/repeat-last")
def repeat_last(body: RepeatIn, user: User = Depends(RESTAURANT_ANY), db: Session = Depends(get_db)):
    last = (db.query(Rescue).filter_by(restaurant_org_id=user.organization_id, is_draft=False)
            .order_by(Rescue.id.desc()).first())
    if last is None:
        raise HTTPException(404, "Nothing to repeat yet")
    deadline = body.pickup_deadline or _same_time_today(last.pickup_deadline)
    return _post_and_match(db, user, posting.body_from_rescue(last, deadline, body.attested))


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    post: posting.QuickPost


@router.post("/restaurants/me/templates")
def save_template(body: TemplateIn, user: User = Depends(RESTAURANT_ANY), db: Session = Depends(get_db)):
    t = RescueTemplate(organization_id=user.organization_id, name=body.name, fields=posting.template_fields(body.post),
                       created_by=user.id, created_at=clock.now())
    db.add(t)
    db.commit()
    return {"id": t.id, "name": t.name, "fields": t.fields}


@router.get("/restaurants/me/templates")
def list_templates(user: User = Depends(RESTAURANT_ANY), db: Session = Depends(get_db)):
    return [{"id": t.id, "name": t.name, "fields": t.fields}
            for t in db.query(RescueTemplate).filter_by(organization_id=user.organization_id).order_by(RescueTemplate.id)]


@router.post("/rescues/from-template/{template_id}")
def post_from_template(template_id: int, body: RepeatIn, user: User = Depends(RESTAURANT_ANY), db: Session = Depends(get_db)):
    t = db.get(RescueTemplate, template_id)
    if t is None or t.organization_id != user.organization_id:
        raise HTTPException(404, "Template not found")
    if body.pickup_deadline is None:
        raise HTTPException(422, "Give a pickup deadline")
    return _post_and_match(db, user, posting.body_from_template(t, body.pickup_deadline, body.attested))


class ScheduleIn(BaseModel):
    template_id: int
    weekday: int = Field(ge=0, le=6, description="0 = Monday")
    local_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


@router.post("/restaurants/me/schedules")
def create_schedule(body: ScheduleIn, user: User = Depends(RESTAURANT_MANAGER), db: Session = Depends(get_db)):
    t = db.get(RescueTemplate, body.template_id)
    if t is None or t.organization_id != user.organization_id:
        raise HTTPException(404, "Template not found")
    s = RecurringSchedule(organization_id=user.organization_id, template_id=t.id, weekday=body.weekday, local_time=body.local_time)
    db.add(s)
    db.commit()
    return {"id": s.id, "template_id": t.id, "weekday": s.weekday, "local_time": s.local_time, "active": s.active}


@router.post("/rescues/{rescue_id}/confirm")
def confirm_draft(rescue_id: int, attested: bool = Body(..., embed=True), user: User = Depends(RESTAURANT_ANY),
                  db: Session = Depends(get_db)):
    """One action to turn a recurring draft into a live post."""
    r = _own(db, rescue_id, user)
    if not r.is_draft:
        raise HTTPException(409, "This rescue is already posted")
    if not attested:
        raise HTTPException(422, "Confirm the food was held at a safe temperature")
    if r.pickup_deadline <= clock.now():
        raise HTTPException(409, "This draft's pickup time has passed")
    r.is_draft, r.attested_by, r.attested_at, r.created_at = False, user.id, clock.now(), clock.now()
    audit.log(db, "rescue_posted", entity="rescue", actor=user, rescue_id=r.id, to_state="posted",
              details={"from_draft": True, "attested_by": user.id})
    match = dispatch.run_matching(db, r, user)
    db.commit()
    return {"rescue": rescue_json(r, user), "matching": match}


@router.get("/rescues")
def list_rescues(status: Optional[str] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Rescue)
    if user.role in ("restaurant_staff", "restaurant_manager"):
        q = q.filter_by(restaurant_org_id=user.organization_id)
    elif user.role != "admin":
        raise HTTPException(403, "Restaurants see their own rescues; volunteers and organizations use their own lists")
    if status:
        q = q.filter_by(status=status)
    return [rescue_json(r, user) for r in q.order_by(Rescue.id.desc()).limit(100)]


@router.get("/rescues/{rescue_id}")
def get_rescue(rescue_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r, only_org = load_rescue(db, rescue_id, user)
    return rescue_json(r, user, only_org)


@router.patch("/rescues/{rescue_id}")
def edit_rescue(rescue_id: int, body: posting.PostEdit, user: User = Depends(RESTAURANT_ANY), db: Session = Depends(get_db)):
    r = _own(db, rescue_id, user)
    changed = posting.edit_post(db, r, user, body)
    if {"quantity", "unit"} & set(changed) and r.status in ("matched", "en_route_pickup"):
        from app import lifecycle
        for t in lifecycle.active_trips(r):
            lifecycle.end_trip(db, t, "reassigned", user, reason="quantity changed before pickup")
        dispatch.requeue(db, r, user, "the quantity changed before pickup")
    db.commit()
    return {"rescue": rescue_json(r, user), "changed": changed}


@router.post("/rescues/{rescue_id}/cancel")
def cancel_rescue(rescue_id: int, reason: str = Body("", embed=True), user: User = Depends(RESTAURANT_ANY),
                  db: Session = Depends(get_db)):
    r = _own(db, rescue_id, user)
    posting.cancel_post(db, r, user, reason)
    db.commit()
    return rescue_json(r, user)


@router.get("/rescues/{rescue_id}/audit")
def rescue_audit(rescue_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r, only_org = load_rescue(db, rescue_id, user)
    if only_org is not None:
        raise HTTPException(404, "Rescue not found")
    from app.models import AuditEvent
    events = db.query(AuditEvent).filter_by(rescue_id=r.id).order_by(AuditEvent.at, AuditEvent.id).all()
    return [audit.event_json(e) for e in events]


@router.get("/rescues/{rescue_id}/matching-explanation")
def matching_explanation(rescue_id: int, attempt: Optional[int] = None, user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    r, only_org = load_rescue(db, rescue_id, user)
    if user.role not in ("admin", "restaurant_staff", "restaurant_manager"):
        raise HTTPException(403, "Matching explanations are for the restaurant and admins")
    from sqlalchemy import func
    latest = attempt or db.query(func.max(MatchingExplanation.attempt)).filter_by(rescue_id=r.id).scalar()
    rows = (db.query(MatchingExplanation, Organization).join(Organization, Organization.id == MatchingExplanation.organization_id)
            .filter(MatchingExplanation.rescue_id == r.id, MatchingExplanation.attempt == latest).all())
    return {
        "rescue_id": r.id, "attempt": latest, "status": r.status,
        "eligible": [{"organization_id": o.id, "name": o.name, "estimated_arrival": iso(m.estimated_arrival_at)} for m, o in rows if m.eligible],
        "ineligible": [{"organization_id": o.id, "name": o.name, "reasons": m.reasons,
                        "groups": sorted({group(x["code"]) for x in m.reasons}),
                        "estimated_arrival": iso(m.estimated_arrival_at)} for m, o in rows if not m.eligible],
        "trips": [{"id": t.id, "mode": t.mode, "simulated": t.simulated, "mode_reason": t.mode_reason, "status": t.status}
                  for t in r.trips],
    }

