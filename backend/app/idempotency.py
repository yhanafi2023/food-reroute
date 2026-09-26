"""Idempotency-Key support for every state-changing request.

A client on a bad connection may send the same "picked up" tap twice. If a POST,
PUT, PATCH or DELETE carries an Idempotency-Key header, the first response is
stored and any retry with the same key from the same caller gets that stored
response back (header Idempotent-Replayed: true) without running the action again.
Reusing a key for a different request is rejected with 422.

/auth/ requests are never stored: their responses carry a session token, and signed-out
callers all share one caller id, so a replay could hand one person's session to another.
"""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app import clock
from app.auth import caller_key
from app.db import SessionLocal
from app.models import IdempotencyRecord

METHODS = ("POST", "PUT", "PATCH", "DELETE")


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        key = request.headers.get("idempotency-key")
        if request.method not in METHODS or not key or request.url.path.startswith("/auth/"):
            return await call_next(request)
        if len(key) > 120:
            return JSONResponse({"detail": "Idempotency-Key is too long (max 120 characters)"}, status_code=422)
        caller = caller_key(request.headers.get("authorization"))
        path = request.url.path
        with SessionLocal() as db:
            rec = db.query(IdempotencyRecord).filter_by(key=key, caller=caller).one_or_none()
            if rec is not None:
                if rec.method != request.method or rec.path != path:
                    return JSONResponse({"detail": "This Idempotency-Key was already used for a different request"},
                                        status_code=422)
                return Response(rec.body, status_code=rec.status_code, media_type="application/json",
                                headers={"Idempotent-Replayed": "true"})
        response = await call_next(request)
        body = b"".join([chunk async for chunk in response.body_iterator])
        if response.status_code < 500:
            with SessionLocal() as db:
                try:
                    db.add(IdempotencyRecord(key=key, caller=caller, method=request.method, path=path,
                                             status_code=response.status_code, body=body.decode("utf-8", "replace"),
                                             created_at=clock.now()))
                    db.commit()
                except IntegrityError:
                    db.rollback()
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return Response(body, status_code=response.status_code, headers=headers, media_type=response.media_type)

