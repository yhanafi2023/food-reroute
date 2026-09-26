from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import create_token, get_current_user, hash_password, verify_password
from app.db import get_db
from app.models import Driver, Organization, Restaurant, User
from app.schemas import LoginIn, SignupIn
from app.serializers import user_json

router = APIRouter(prefix="/auth", tags=["auth"])

FIU = (25.7574, -80.3733)  # default location when the browser does not share one


@router.post("/signup")
def signup(body: SignupIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "An account with this email already exists")
    user = User(name=body.name.strip(), email=email, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.flush()
    lat, lng = (body.lat, body.lng) if body.lat is not None and body.lng is not None else FIU
    address = body.address or ""
    if body.role == "RESTAURANT":
        db.add(Restaurant(user_id=user.id, name=user.name, address=address, lat=lat, lng=lng))
    elif body.role == "DRIVER":
        db.add(Driver(user_id=user.id, name=user.name, lat=lat, lng=lng, is_available=True, capacity_meals=60))
    else:
        db.add(Organization(user_id=user.id, name=user.name, address=address, lat=lat, lng=lng))
    db.commit()
    return {"token": create_token(user), "user": user_json(user)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=body.email.lower()).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect")
    return {"token": create_token(user), "user": user_json(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_json(user)
