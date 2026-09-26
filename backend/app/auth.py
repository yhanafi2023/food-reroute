"""Password hashing (salted PBKDF2-SHA256), JWT with a role claim, and FastAPI dependencies."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import JWT_EXPIRE_HOURS, JWT_SECRET
from app.db import get_db
from app.models import Driver, Organization, Restaurant, User

ITERATIONS = 120_000
ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str, salt: bytes = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_b64, digest_b64 = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iterations))
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer), db: Session = Depends(get_db)
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session expired, please log in again")
    user = db.get(User, int(payload["sub"]))
    if user is None or user.role != payload.get("role"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in")
    return user


def require_role(*roles: str) -> Callable[..., User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"This action is for {' or '.join(r.lower() for r in roles)} accounts")
        return user

    return dependency


def restaurant_of(db: Session, user: User) -> Restaurant:
    r = db.query(Restaurant).filter_by(user_id=user.id).one_or_none()
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No restaurant profile for this account")
    return r


def driver_of(db: Session, user: User) -> Driver:
    d = db.query(Driver).filter_by(user_id=user.id).one_or_none()
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No driver profile for this account")
    return d


def organization_of(db: Session, user: User) -> Organization:
    o = db.query(Organization).filter_by(user_id=user.id).one_or_none()
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No organization profile for this account")
    return o
