"""Sign-in, registration, and organization membership (section 1)."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app import audit
from app.auth import (
    PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, authenticate, create_token, get_current_user, hash_password, user_json,
)
from app.db import get_db
from app.models import Organization, ReceiverProfile, RestaurantProfile, User, VolunteerProfile

router = APIRouter(tags=["auth"])

NewPassword = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class RegisterOrgIn(BaseModel):
    kind: Literal["restaurant", "receiver"]
    organization_name: str = Field(min_length=1, max_length=160)
    legal_name: str = Field(default="", max_length=200)
    address: str = Field(default="", max_length=255)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    manager_name: str = Field(min_length=1, max_length=160)
    manager_email: EmailStr
    manager_password: NewPassword
    manager_phone: str = Field(default="", max_length=40)


class RegisterVolunteerIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr
    password: NewPassword
    phone: str = Field(default="", max_length=40)
    home_lat: float = Field(ge=-90, le=90)
    home_lng: float = Field(ge=-180, le=180)


class MemberIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=160)
    password: NewPassword  # set by the manager and handed to the new member (no invite email)
    phone: str = Field(default="", max_length=40)
    manager: bool = False


def _email_free(db: Session, email: str) -> str:
    email = email.strip().lower()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "An account with this email already exists. Log in instead.")
    return email


def _session(user: User) -> dict:
    return {"token": create_token(user), "user": user_json(user)}


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    return _session(authenticate(db, body.email, body.password))


@router.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return user_json(user)


@router.post("/auth/register-organization")
def register_org(body: RegisterOrgIn, db: Session = Depends(get_db)):
    email = _email_free(db, body.manager_email)
    org = Organization(kind=body.kind, name=body.organization_name.strip(), legal_name=body.legal_name.strip(),
                       address=body.address.strip(), lat=body.lat, lng=body.lng)
    db.add(org)
    db.flush()
    db.add(RestaurantProfile(organization_id=org.id) if body.kind == "restaurant" else ReceiverProfile(organization_id=org.id))
    role = "restaurant_manager" if body.kind == "restaurant" else "org_manager"
    user = User(email=email, password_hash=hash_password(body.manager_password), name=body.manager_name.strip(),
                first_name=body.manager_name.split()[0], role=role, organization_id=org.id, phone=body.manager_phone)
    db.add(user)
    db.flush()
    audit.log(db, "organization_registered", entity="organization", actor=user, details={"organization_id": org.id})
    db.commit()
    return {**_session(user), "organization_id": org.id,
            "next": "You are signed in." + (" Answer the three onboarding questions before deliveries can be "
                                             "routed to you." if body.kind == "receiver" else "")}


@router.post("/auth/register-volunteer")
def register_volunteer(body: RegisterVolunteerIn, db: Session = Depends(get_db)):
    email = _email_free(db, body.email)
    user = User(email=email, password_hash=hash_password(body.password), name=body.name.strip(),
                first_name=body.name.split()[0], role="volunteer", phone=body.phone)
    db.add(user)
    db.flush()
    db.add(VolunteerProfile(user_id=user.id, home_lat=body.home_lat, home_lng=body.home_lng))
    db.commit()
    return {**_session(user), "next": "You are signed in. Set your availability next."}


def _manager(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("restaurant_manager", "org_manager"):
        raise HTTPException(403, "Only managers can manage staff")
    return user


@router.get("/orgs/me/members")
def list_members(user: User = Depends(_manager), db: Session = Depends(get_db)):
    members = db.query(User).filter_by(organization_id=user.organization_id).order_by(User.id).all()
    return [{**user_json(m), "active": m.active} for m in members]


@router.post("/orgs/me/members")
def add_member(body: MemberIn, user: User = Depends(_manager), db: Session = Depends(get_db)):
    email = _email_free(db, body.email)
    prefix = "restaurant" if user.role == "restaurant_manager" else "org"
    role = f"{prefix}_{'manager' if body.manager else 'staff'}"
    member = User(email=email, password_hash=hash_password(body.password), name=body.name.strip(),
                  first_name=body.name.split()[0], role=role, organization_id=user.organization_id, phone=body.phone)
    db.add(member)
    db.flush()
    audit.log(db, "member_added", entity="user", actor=user, details={"member_id": member.id, "role": role})
    db.commit()
    return user_json(member)


@router.delete("/orgs/me/members/{member_id}")
def remove_member(member_id: int, user: User = Depends(_manager), db: Session = Depends(get_db)):
    member = db.get(User, member_id)
    if member is None or member.organization_id != user.organization_id:
        raise HTTPException(404, "Member not found")
    if member.id == user.id:
        raise HTTPException(400, "You cannot remove yourself")
    member.active = False
    audit.log(db, "member_deactivated", entity="user", actor=user, details={"member_id": member.id})
    db.commit()
    return {"ok": True}

