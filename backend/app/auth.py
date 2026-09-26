"""Passwordless sign-in (email code or magic link), JWT sessions, and permission checks.

Flow: POST /auth/request-code {email} sends a 6 digit code and a magic link through
the notification service (console by default). POST /auth/verify with the code or
the link token returns a JWT carrying the user's role and organization.
Codes expire after 10 minutes and allow 5 attempts. Unknown emails get the same
response as known ones, so the endpoint does not reveal who has an account.

Demo accounts (seed file) may also use the demo code from app/seed.py, only while
DEMO_MODE is on.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Callable, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app import clock, notify
from app.config import DEMO_MODE, FRONTEND_URL, JWT_EXPIRE_HOURS, JWT_SECRET
from app.db import get_db
from app.models import ORG_ROLES, RESTAURANT_ROLES, LoginToken, User

ALGORITHM = "HS256"
CODE_TTL_MIN = 10
MAX_ATTEMPTS = 5
_bearer = HTTPBearer(auto_error=False)


def _hash(value: str) -> str:
    return hmac.new(JWT_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()


def request_code(db: Session, email: str) -> None:
    user = db.query(User).filter_by(email=email.strip().lower(), active=True).one_or_none()
    if user is None:
        return
    code = f"{secrets.randbelow(10 ** 6):06d}"
    link = secrets.token_urlsafe(24)
    db.add(LoginToken(user_id=user.id, code_hash=_hash(code), link_hash=_hash(link),
                      expires_at=clock.now() + timedelta(minutes=CODE_TTL_MIN), created_at=clock.now()))
    notify.send(db, [user], "login_code", "Your FoodFlow sign-in code",
                f"Code {code} (valid {CODE_TTL_MIN} minutes). Or open {FRONTEND_URL}/auth/callback?token={link}")
    db.commit()


def verify(db: Session, email: Optional[str], code: Optional[str], link_token: Optional[str]) -> User:
    from app.seed import DEMO_CODE  # demo accounts only; see module docstring

    now = clock.now()
    if link_token:
        tok = db.query(LoginToken).filter_by(link_hash=_hash(link_token)).one_or_none()
        if tok is None or tok.used_at or tok.expires_at < now:
            raise HTTPException(401, "This sign-in link has expired. Request a new one.")
        tok.used_at = now
        user = db.get(User, tok.user_id)
        db.commit()
        return user
    user = db.query(User).filter_by(email=(email or "").strip().lower(), active=True).one_or_none()
    if user is None or not code:
        raise HTTPException(401, "That code is not valid. Request a new one.")
    if DEMO_MODE and user.is_demo_account and hmac.compare_digest(code, DEMO_CODE):
        return user
    tok = (db.query(LoginToken).filter(LoginToken.user_id == user.id, LoginToken.used_at.is_(None),
                                        LoginToken.expires_at >= now)
           .order_by(LoginToken.id.desc()).first())
    if tok is None:
        raise HTTPException(401, "That code is not valid. Request a new one.")
    tok.attempts += 1
    if tok.attempts > MAX_ATTEMPTS:
        tok.used_at = now
        db.commit()
        raise HTTPException(429, "Too many attempts. Request a new code.")
    if not hmac.compare_digest(tok.code_hash, _hash(code)):
        db.commit()
        raise HTTPException(401, "That code is not valid. Request a new one.")
    tok.used_at = now
    db.commit()
    return user


def create_token(user: User) -> str:
    payload = {"sub": str(user.id), "role": user.role, "org": user.organization_id,
               "exp": clock.now() + timedelta(hours=JWT_EXPIRE_HOURS)}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def caller_key(authorization: Optional[str]) -> str:
    """Stable caller id for idempotency records (user id, or 'anon')."""
    if authorization and authorization.lower().startswith("bearer "):
        try:
            payload = jwt.decode(authorization[7:], JWT_SECRET, algorithms=[ALGORITHM],
                                 options={"verify_exp": False})
            return f"user:{payload['sub']}"
        except jwt.PyJWTError:
            return "anon"
    return "anon"


def get_current_user(creds: HTTPAuthorizationCredentials = Depends(_bearer), db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[ALGORITHM],
                             options={"verify_exp": False})
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in again")
    if payload.get("exp", 0) < clock.now().timestamp():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session expired, please sign in again")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.active or user.role != payload.get("role"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in")
    return user


def require_role(*roles: str) -> Callable[..., User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account cannot do this")
        return user

    return dependency


RESTAURANT_ANY = require_role(*RESTAURANT_ROLES)
RESTAURANT_MANAGER = require_role("restaurant_manager")
ORG_ANY = require_role(*ORG_ROLES)
ORG_MANAGER = require_role("org_manager")
VOLUNTEER = require_role("volunteer")
ADMIN = require_role("admin")


def mask_phone(phone: str) -> str:
    digits = [c for c in phone if c.isdigit()]
    return f"***-***-{''.join(digits[-4:])}" if len(digits) >= 4 else "not provided"


def volunteer_public(user: Optional[User], vehicle: str = "") -> Optional[dict]:
    """What restaurants and orgs may see about a volunteer: first name, vehicle, masked contact."""
    if user is None:
        return None
    return {"first_name": user.first_name or user.name.split(" ")[0], "vehicle": vehicle,
            "contact": mask_phone(user.phone)}


def user_json(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "first_name": u.first_name, "role": u.role,
            "organization_id": u.organization_id}
