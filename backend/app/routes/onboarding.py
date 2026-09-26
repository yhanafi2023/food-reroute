"""Onboarding intake (section 2): receiving orgs' three questions, restaurant and volunteer profiles."""
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app import audit, clock, intake
from app.auth import ORG_ANY, RESTAURANT_MANAGER, VOLUNTEER, get_current_user, mask_phone
from app.db import get_db
from app.models import Organization, ReceiverProfile, ReceivingException, RestaurantProfile, User, VolunteerProfile

router = APIRouter(tags=["onboarding"])


def _org_manager(user: User = Depends(get_current_user)) -> User:
    if user.role != "org_manager":
        raise HTTPException(403, "Only an organization manager can change onboarding answers")
    return user


def profile_json(db: Session, org: Organization, viewer: User) -> Dict:
    p = org.receiver_profile
    own = viewer.organization_id == org.id or viewer.role == "admin"
    exceptions = db.query(ReceivingException).filter_by(organization_id=org.id).order_by(ReceivingException.day).all()
    return {
        "organization": {"id": org.id, "name": org.name, "legal_name": org.legal_name, "address": org.address,
                         "lat": org.lat, "lng": org.lng, "is_fictional": org.is_fictional},
        "q1": {"schedule": p.schedule, "exceptions": [{"day": e.day.isoformat(), "reason": e.reason} for e in exceptions],
               "cutoff_minutes": p.cutoff_minutes, "receiving_contact_name": p.receiving_contact_name,
               "receiving_contact_phone": p.receiving_contact_phone if own else mask_phone(p.receiving_contact_phone),
               "receiving_instructions": p.receiving_instructions, "curbside_ok": p.curbside_ok,
               "curb_location": p.curb_location},
        "q2": {k: getattr(p, k) for k in ("accepts_hot", "hot_max_minutes", "can_hold_hot", "serves_immediately",
                                           "accepts_cold", "fridge_capacity_meals", "accepts_frozen", "freezer_capacity_meals",
                                           "accepts_shelf_stable", "dietary_rules", "refused_allergens",
                                           "max_meals_per_delivery", "typical_nightly_need", "current_need")},
        "q3": {"required_fields": p.required_fields, "report_frequency": p.report_frequency,
               "report_format": p.report_format, "reports_to": p.reports_to, "is_501c3": p.is_501c3,
               "ein": p.ein if own else None, "acknowledgment_frequency": p.ack_frequency,
               "qualified_donee_verified": p.ein_verified, "verification_source": p.verification_source},
        "completeness": intake.completeness(db, org.id),
    }


@router.put("/orgs/me/intake/{question}")
def answer_question(question: Literal["Q1", "Q2", "Q3"], answers: dict = Body(...), user: User = Depends(_org_manager),
                    db: Session = Depends(get_db)):
    try:
        parsed = intake.SCHEMAS[question](**answers)
    except ValidationError as e:
        raise HTTPException(422, [{"loc": list(err["loc"]), "msg": err["msg"]} for err in e.errors()])
    intake.save_answers(db, user.organization_id, question, parsed, user)
    audit.log(db, f"intake_{question.lower()}_answered", entity="organization", actor=user,
              details={"organization_id": user.organization_id})
    db.commit()
    org = db.get(Organization, user.organization_id)
    return profile_json(db, org, user)


@router.post("/orgs/me/intake/confirm")
def confirm_intake(user: User = Depends(_org_manager), db: Session = Depends(get_db)):
    if not intake.is_complete(db, user.organization_id):
        raise HTTPException(409, "Answer all three onboarding questions first")
    intake.confirm(db, user.organization_id)
    audit.log(db, "intake_confirmed", entity="organization", actor=user, details={"organization_id": user.organization_id})
    db.commit()
    return intake.completeness(db, user.organization_id)


@router.get("/orgs/me/profile")
def my_org_profile(user: User = Depends(ORG_ANY), db: Session = Depends(get_db)):
    return profile_json(db, db.get(Organization, user.organization_id), user)


@router.get("/orgs/{org_id}/profile-completeness")
def profile_completeness(org_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = db.get(Organization, org_id)
    if org is None or org.kind != "receiver" or (user.role != "admin" and user.organization_id != org_id):
        raise HTTPException(404, "Organization not found")
    return intake.completeness(db, org_id)


class NeedIn(BaseModel):
    meals: int = Field(ge=0, le=10000)


@router.post("/orgs/me/need")
def update_need(body: NeedIn, user: User = Depends(ORG_ANY), db: Session = Depends(get_db)):
    """Quick update: 'we need 40 tonight'."""
    p = db.get(ReceiverProfile, user.organization_id)
    p.current_need, p.current_need_at = body.meals, clock.now()
    audit.log(db, "need_updated", entity="organization", actor=user, details={"meals": body.meals})
    db.commit()
    return {"current_need": p.current_need, "updated_at": p.current_need_at.isoformat() + "Z"}


# ---------- 2b restaurants ----------



class RestaurantProfileIn(BaseModel):
    closing_times: Dict[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"], str]
    staffed_until: Dict[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"], str]
    surplus_usually: str = Field(default="", max_length=200)
    totes_on_hand: int = Field(ge=0, le=500)
    pickup_instructions: str = Field(default="", max_length=1000)
    hauling_cost_per_lb: Optional[float] = Field(default=None, ge=0, le=100)
    public_partner_page: bool = False

    @field_validator("closing_times", "staffed_until")
    @classmethod
    def _times(cls, v):
        for t in v.values():
            if not intake.TIME_RE.match(t) or t == "24:00":
                raise ValueError("times are HH:MM (use 00:00 for midnight)")
        return v


def restaurant_profile_json(org: Organization) -> Dict:
    p = org.restaurant_profile
    return {"organization": {"id": org.id, "name": org.name, "address": org.address, "is_fictional": org.is_fictional},
            **{k: getattr(p, k) for k in ("closing_times", "staffed_until", "surplus_usually", "totes_on_hand", "totes_out",
                                           "pickup_instructions", "hauling_cost_per_lb", "public_partner_page")},
            "public_slug": org.public_slug}


@router.get("/restaurants/me/profile")
def get_restaurant_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ("restaurant_staff", "restaurant_manager"):
        raise HTTPException(403, "Your account cannot do this")
    return restaurant_profile_json(db.get(Organization, user.organization_id))


@router.put("/restaurants/me/profile")
def put_restaurant_profile(body: RestaurantProfileIn, user: User = Depends(RESTAURANT_MANAGER), db: Session = Depends(get_db)):
    org = db.get(Organization, user.organization_id)
    p = org.restaurant_profile
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    p.updated_at = clock.now()
    if body.public_partner_page and not org.public_slug:
        org.public_slug = f"{org.name.lower().replace(' ', '-')}-{org.id}"
    audit.log(db, "restaurant_profile_updated", entity="organization", actor=user, details={"organization_id": org.id})
    db.commit()
    return restaurant_profile_json(org)


# ---------- 2c volunteers ----------

class VolunteerProfileIn(BaseModel):
    availability: Dict[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"], List[List[str]]]
    max_distance_mi: float = Field(gt=0, le=50)
    capacity_meals: int = Field(gt=0, le=500)
    has_cooler: bool
    has_insulated_bags: bool
    preferred_areas: str = Field(default="", max_length=200)
    vehicle_description: str = Field(min_length=1, max_length=120)

    @field_validator("availability")
    @classmethod
    def _windows(cls, v):
        for windows in v.values():
            intake._check_windows(windows)
        return v


def volunteer_profile_json(v: VolunteerProfile) -> Dict:
    return {k: getattr(v, k) for k in ("availability", "max_distance_mi", "capacity_meals", "has_cooler",
                                        "has_insulated_bags", "preferred_areas", "vehicle_description")}


@router.get("/volunteers/me/profile")
def get_volunteer_profile(user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    return volunteer_profile_json(db.get(VolunteerProfile, user.id))


@router.put("/volunteers/me/profile")
def put_volunteer_profile(body: VolunteerProfileIn, user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    v = db.get(VolunteerProfile, user.id)
    for k, val in body.model_dump().items():
        setattr(v, k, val)
    db.commit()
    return volunteer_profile_json(v)


