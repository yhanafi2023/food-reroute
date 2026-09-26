"""Posting that fits a real kitchen (section 3).

A quick post needs only quantity, unit, category, pickup deadline and the staff
food-safety attestation. Units convert to estimated meals with UNIT_TO_MEALS
(an assumption); both the original unit and the estimate are stored.
safe_until defaults from SAFE_UNTIL_HOURS by category.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app import audit, clock, lifecycle, notify
from app.assumptions import DUPLICATE_WINDOW_MIN, SAFE_UNTIL_HOURS, UNIT_TO_MEALS
from app.intake import ALLERGENS, DIETARY_TAGS
from app.models import Rescue, RescueTemplate, User
from app.schemas_common import to_naive_utc

Unit = Literal["individual_meal", "bag", "box", "tray", "half_pan", "full_pan"]
Category = Literal["hot", "cold", "frozen", "shelf_stable"]


class QuickPost(BaseModel):
    quantity: float = Field(gt=0, le=1000)
    unit: Unit
    category: Category
    pickup_deadline: datetime
    attested: bool = Field(description="Staff confirm the food was held at a safe temperature")
    description: str = Field(default="", max_length=1000)
    prepared_at: Optional[datetime] = None
    allergens: Optional[List[Literal[ALLERGENS]]] = None  # type: ignore[valid-type]  # None = not declared
    dietary_tags: List[Literal[DIETARY_TAGS]] = []  # type: ignore[valid-type]
    pickup_instructions: Optional[str] = Field(default=None, max_length=1000)
    safe_until: Optional[datetime] = None
    fmv_per_meal: Optional[float] = Field(default=None, ge=0, le=500)
    cost_basis_per_meal: Optional[float] = Field(default=None, ge=0, le=500)

    _utc = field_validator("pickup_deadline", "prepared_at", "safe_until")(lambda v: to_naive_utc(v) if v else v)


class PostEdit(BaseModel):
    quantity: Optional[float] = Field(default=None, gt=0, le=1000)
    unit: Optional[Unit] = None
    description: Optional[str] = Field(default=None, max_length=1000)
    allergens: Optional[List[Literal[ALLERGENS]]] = None  # type: ignore[valid-type]
    dietary_tags: Optional[List[Literal[DIETARY_TAGS]]] = None  # type: ignore[valid-type]
    pickup_deadline: Optional[datetime] = None
    pickup_instructions: Optional[str] = Field(default=None, max_length=1000)

    _utc = field_validator("pickup_deadline")(lambda v: to_naive_utc(v) if v else v)


def est_meals(quantity: float, unit: str) -> int:
    return max(int(round(quantity * UNIT_TO_MEALS[unit])), 1)


def _defaults(user: User) -> Dict[str, Any]:
    prof = user.organization.restaurant_profile
    return {"pickup_instructions": prof.pickup_instructions if prof else "",
            "fmv": prof.default_fmv_per_meal if prof else None, "basis": prof.default_cost_basis_per_meal if prof else None}


def create_post(db: Session, user: User, body: QuickPost, draft: bool = False, schedule_id: Optional[int] = None) -> Dict[str, Any]:
    now = clock.now()
    if not draft and not body.attested:
        raise HTTPException(422, "Confirm the food was held at a safe temperature before posting")
    prepared = body.prepared_at or now
    safe_until = body.safe_until or prepared + timedelta(hours=SAFE_UNTIL_HOURS[body.category])
    if safe_until <= now:
        raise HTTPException(422, "This food is already past its safe-until time and cannot be donated")
    if not draft and body.pickup_deadline <= now:
        raise HTTPException(422, "The pickup deadline must be in the future")
    deadline = min(body.pickup_deadline, safe_until)
    d = _defaults(user)
    rescue = Rescue(
        restaurant_org_id=user.organization_id, posted_by=user.id, status="posted", quantity=body.quantity, unit=body.unit,
        meals_per_unit=UNIT_TO_MEALS[body.unit], est_meals=est_meals(body.quantity, body.unit), category=body.category,
        description=body.description, prepared_at=body.prepared_at, allergens=body.allergens or [],
        allergens_declared=body.allergens is not None, dietary_tags=body.dietary_tags,
        attested_by=None if draft else user.id, attested_at=None if draft else now, safe_until=safe_until,
        pickup_deadline=deadline, pickup_instructions=body.pickup_instructions if body.pickup_instructions is not None else d["pickup_instructions"],
        pickup_code=lifecycle.code(), is_draft=draft, schedule_id=schedule_id,
        fmv_per_meal=body.fmv_per_meal if body.fmv_per_meal is not None else d["fmv"],
        cost_basis_per_meal=body.cost_basis_per_meal if body.cost_basis_per_meal is not None else d["basis"],
        is_fictional=user.organization.is_fictional, created_at=now, updated_at=now,
    )
    warnings = []
    dup = find_duplicate(db, user.organization_id, body)
    if dup is not None:
        rescue.duplicate_of = dup.id
        warnings.append(f"This looks like rescue #{dup.id} posted {int((now - dup.created_at).total_seconds() // 60)} min ago "
                        f"({dup.quantity:g} {dup.unit.replace('_', ' ')}, {dup.category}). Cancel one if it is a double post.")
    if deadline < body.pickup_deadline:
        warnings.append(f"Pickup deadline moved to the food's safe-until time, {clock.fmt_local(deadline)}")
    db.add(rescue)
    db.flush()
    audit.log(db, "rescue_drafted" if draft else "rescue_posted", entity="rescue", actor=user, rescue_id=rescue.id,
              to_state="posted", details={"quantity": body.quantity, "unit": body.unit, "est_meals": rescue.est_meals,
                                          "meals_per_unit_assumption": rescue.meals_per_unit, "category": body.category,
                                          "attested_by": rescue.attested_by, "duplicate_of": rescue.duplicate_of})
    if dup is not None:
        notify.send(db, [user], "duplicate_warning", "Possible double post", warnings[0], dedupe=f"dup:{rescue.id}")
    return {"rescue": rescue, "warnings": warnings}


def find_duplicate(db: Session, org_id: int, body: QuickPost) -> Optional[Rescue]:
    since = clock.now() - timedelta(minutes=DUPLICATE_WINDOW_MIN)
    recent = (db.query(Rescue).filter(Rescue.restaurant_org_id == org_id, Rescue.created_at >= since,
                                      Rescue.status.notin_(("cancelled", "expired")), Rescue.is_draft.is_(False))
              .order_by(Rescue.id.desc()).all())
    for r in recent:
        if r.category == body.category and r.unit == body.unit and abs(r.quantity - body.quantity) <= max(0.1 * r.quantity, 0.5):
            return r
    return None


def body_from_rescue(r: Rescue, deadline: datetime, attested: bool) -> QuickPost:
    return QuickPost(quantity=r.quantity, unit=r.unit, category=r.category, pickup_deadline=deadline, attested=attested,
                     description=r.description, allergens=r.allergens if r.allergens_declared else None,
                     dietary_tags=r.dietary_tags, pickup_instructions=r.pickup_instructions)


def template_fields(body: QuickPost) -> Dict[str, Any]:
    return {k: v for k, v in body.model_dump(mode="json").items()
            if k not in ("pickup_deadline", "attested", "prepared_at", "safe_until")}


def body_from_template(t: RescueTemplate, deadline: datetime, attested: bool) -> QuickPost:
    return QuickPost(**{**t.fields, "pickup_deadline": deadline, "attested": attested})


def edit_post(db: Session, rescue: Rescue, user: User, body: PostEdit) -> List[str]:
    if rescue.status not in ("posted", "matched", "en_route_pickup"):
        raise HTTPException(409, f"This rescue is {rescue.status.replace('_', ' ')}; it can be changed only before pickup")
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if getattr(rescue, k, None) != v}
    if "allergens" in changes:
        rescue.allergens_declared = changes["allergens"] is not None
        changes["allergens"] = changes["allergens"] or []
    for k, v in changes.items():
        setattr(rescue, k, v)
    if "quantity" in changes or "unit" in changes:
        rescue.meals_per_unit = UNIT_TO_MEALS[rescue.unit]
        rescue.est_meals = est_meals(rescue.quantity, rescue.unit)
    if "pickup_deadline" in changes:
        if rescue.pickup_deadline <= clock.now():
            raise HTTPException(422, "The pickup deadline must be in the future")
        rescue.pickup_deadline = min(rescue.pickup_deadline, rescue.safe_until)
    rescue.updated_at = clock.now()
    audit.log(db, "rescue_edited", entity="rescue", actor=user, rescue_id=rescue.id,
              details={k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in changes.items()})
    carriers = [t.volunteer for t in lifecycle.active_trips(rescue) if t.volunteer]
    if changes and carriers:
        notify.send(db, carriers, "matched", "A rescue you are carrying changed",
                    f"Rescue #{rescue.id} was edited: {', '.join(changes)}.", dedupe=f"edit:{rescue.id}:{rescue.updated_at.isoformat()}")
    return list(changes)


def cancel_post(db: Session, rescue: Rescue, user: User, reason: str) -> None:
    if rescue.status not in ("posted", "matched", "en_route_pickup"):
        raise HTTPException(409, f"This rescue is {rescue.status.replace('_', ' ')}; it can be cancelled only before pickup")
    affected = []
    for trip in lifecycle.active_trips(rescue):
        if trip.volunteer:
            affected.append(trip.volunteer)
        lifecycle.end_trip(db, trip, "cancelled", user, reason="restaurant cancelled")
        for s in trip.stops:
            affected.extend(db.query(User).filter_by(organization_id=s.organization_id, active=True).all())
    rescue.cancel_reason = reason
    lifecycle.set_rescue_status(db, rescue, "cancelled", user, reason=reason)
    notify.send(db, affected, "cancelled", "Pickup cancelled",
                f"{rescue.restaurant.name} cancelled rescue #{rescue.id}" + (f": {reason}" if reason else "") +
                ". Your trip is closed.", dedupe=f"cancel:{rescue.id}")
