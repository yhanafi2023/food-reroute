"""Email and password sign-in, JWT sessions, and permission checks.

Flow: registration stores the email and a salted PBKDF2-SHA256 hash of the password
(users.password_hash; the password itself is never stored). POST /auth/login
{email, password} returns a JWT carrying the user's role and organization. A wrong
password and an unknown email get the same answer. No email is ever sent.

The stored hash records its own iteration count, so PASSWORD_ITERATIONS can be raised
later without breaking existing passwords.

Demo accounts (seed file) share the published DEMO_PASSWORD from app/seed.py and can
sign in only while DEMO_MODE is on.

Throttle: after MAX_FAILURES_PER_EMAIL failed attempts for one email, or MAX_FAILURES_PER_IP
from one address, within THROTTLE_WINDOW_MIN, sign-in answers 429 until the window passes.
A successful sign-in clears that email's failures.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Callable, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app import clock
from app.config import DEMO_MODE, JWT_EXPIRE_HOURS, JWT_SECRET, SERVERLESS
from app.db import get_db
from app.models import ORG_ROLES, RESTAURANT_ROLES, LoginAttempt, User

ALGORITHM = "HS256"
PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 600_000  # OWASP guidance for PBKDF2-HMAC-SHA256
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
THROTTLE_WINDOW_MIN = 15
MAX_FAILURES_PER_EMAIL = 10
MAX_FAILURES_PER_IP = 50
_bearer = HTTPBearer(auto_error=False)

#def password
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    # Verify the password by hashing it with the same PBKDF2 settings
    # and comparing the resulting hash with the securely stored hash.
    try:
        scheme, iterations, salt, digest = stored.split("$")
        if scheme != PASSWORD_SCHEME:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(actual, base64.b64decode(digest))
    except ValueError:  # malformed hash (includes bad base64)
        return False


def client_ip(request: Request) -> Optional[str]:
    """Behind Vercel the socket peer is Vercel's proxy, which sets x-real-ip to the caller; elsewhere trust the peer."""
    if SERVERLESS and request.headers.get("x-real-ip"):
        return request.headers["x-real-ip"]
    return request.client.host if request.client else None


def authenticate(db: Session, email: str, password: str, client_ip: Optional[str] = None) -> User:
    email = email.strip().lower()
    keys = {f"email:{email}": MAX_FAILURES_PER_EMAIL}
    if client_ip:
        keys[f"ip:{client_ip}"] = MAX_FAILURES_PER_IP
    since = clock.now() - timedelta(minutes=THROTTLE_WINDOW_MIN)
    for key, limit in keys.items():
        if db.query(LoginAttempt).filter(LoginAttempt.key == key, LoginAttempt.at >= since).count() >= limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                f"Too many failed sign-in attempts. Try again in {THROTTLE_WINDOW_MIN} minutes.")
    user = db.query(User).filter_by(email=email, active=True).one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        db.add_all([LoginAttempt(key=key, at=clock.now()) for key in keys])
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    db.query(LoginAttempt).filter(LoginAttempt.key == f"email:{email}").delete()
    db.commit()
    if user.is_demo_account and not DEMO_MODE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Demo accounts can sign in only while DEMO_MODE is on")
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
        # Hide all but the last four digits of the phone number for privacy.
    digits = [c for c in phone if c.isdigit()]
    return f"***-***-{''.join(digits[-4:])}" if len(digits) >= 4 else "not provided"


def volunteer_public(user: Optional[User], vehicle: str = "") -> Optional[dict]:
    # Return only the volunteer information that restaurants and organizations are allowed to see.
    if user is None:
        return None
    return {"first_name": user.first_name or user.name.split(" ")[0], "vehicle": vehicle,
            "contact": mask_phone(user.phone)}


def user_json(u: User) -> dict:
        # Convert a User object into a dictionary containing the user's basic account and role information.
    return {"id": u.id, "email": u.email, "name": u.name, "first_name": u.first_name, "role": u.role,
            "organization_id": u.organization_id}
