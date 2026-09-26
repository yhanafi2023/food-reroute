"""Supabase Auth access tokens, accepted alongside FoodFlow's own sessions (app/auth.py).

This is @supabase/server's auth: 'user' mode in Python. A token's signature is checked against the
project's JWKS (SUPABASE_JWKS_URL; asymmetric keys only, so the project needs JWT signing keys, not the
legacy shared secret), and its issuer and audience are pinned to SUPABASE_URL/auth/v1 and "authenticated",
so a token from any other project is refused.

Linking: users.supabase_user_id holds the Supabase user id (the token's sub). The first time an unlinked
Supabase user calls the API, Supabase's GET /auth/v1/user (sent with SUPABASE_PUBLISHABLE_KEY and the
caller's own token) says whether Supabase has confirmed their email. Only a confirmed email is linked, to
the active FoodFlow account with that email that has no Supabase user yet. The token's email claim is never
trusted for this. A Supabase user without a FoodFlow account gets 401: registration stays in FoodFlow.
"""
from __future__ import annotations

from datetime import timezone
from functools import lru_cache
from typing import Optional

import httpx
import jwt
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app import audit, clock, config
from app.models import User

ALGORITHMS = ["ES256", "RS256"]  # Supabase's asymmetric signing keys; HS256 tokens are FoodFlow's own
AUDIENCE = "authenticated"


def enabled() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_JWKS_URL and config.SUPABASE_PUBLISHABLE_KEY)


def is_supabase_token(token: str) -> bool:
    try:
        return enabled() and jwt.get_unverified_header(token).get("alg") in ALGORITHMS
    except jwt.PyJWTError:
        return False


@lru_cache(maxsize=4)
def _jwks(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=600, timeout=config.SERVICE_TIMEOUT_SECONDS)


def verify(token: str, check_exp: bool = True) -> dict:
    """Claims of a genuine token from this project. Raises jwt.PyJWTError otherwise, or
    jwt.PyJWKClientConnectionError when the JWKS cannot be fetched."""
    key = _jwks(config.SUPABASE_JWKS_URL).get_signing_key_from_jwt(token)
    claims = jwt.decode(token, key, algorithms=ALGORITHMS, audience=AUDIENCE,
                        issuer=f"{config.SUPABASE_URL}/auth/v1",
                        options={"require": ["exp", "sub", "iss", "aud"], "verify_exp": False})
    # expiry against the app clock, like FoodFlow's own tokens
    if check_exp and claims["exp"] < clock.now().replace(tzinfo=timezone.utc).timestamp():
        raise jwt.ExpiredSignatureError("Signature has expired")
    return claims


def _confirmed_email(token: str) -> Optional[str]:
    """Supabase's own record of the caller: their email, if Supabase has confirmed it."""
    try:
        r = httpx.get(f"{config.SUPABASE_URL}/auth/v1/user", timeout=config.SERVICE_TIMEOUT_SECONDS,
                      headers={"apikey": config.SUPABASE_PUBLISHABLE_KEY, "Authorization": f"Bearer {token}"})
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Supabase sign-in is unavailable, try again shortly")
    if r.status_code != 200:  # e.g. the session was signed out on Supabase
        return None
    body = r.json()
    email = (body.get("email") or "").strip().lower()
    return email if email and body.get("email_confirmed_at") else None


def _link(db: Session, token: str, supabase_user_id: str) -> Optional[User]:
    email = _confirmed_email(token)
    if email is None:
        return None
    user = db.query(User).filter_by(email=email, active=True, supabase_user_id=None).one_or_none()
    if user is not None:
        user.supabase_user_id = supabase_user_id
        audit.log(db, "supabase_account_linked", entity="user", actor=user)
        db.commit()
    return user


def current_user(db: Session, token: str) -> User:
    try:
        claims = verify(token)
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Supabase sign-in is unavailable, try again shortly")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session expired, please sign in again")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in again")
    user = db.query(User).filter_by(supabase_user_id=claims["sub"]).one_or_none() or _link(db, token, claims["sub"])
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "No FoodFlow account matches this sign-in. Confirm your email with Supabase, "
                            "or register with FoodFlow using the same email first.")
    if user.is_demo_account and not config.DEMO_MODE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Demo accounts can sign in only while DEMO_MODE is on")
    return user
