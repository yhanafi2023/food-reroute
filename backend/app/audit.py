"""Append-only audit log helpers: every state change and edit, who did it, when, where."""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app import clock
from app.models import AuditEvent, User


def log(db: Session, action: str, *, entity: str, actor: Optional[User] = None, rescue_id: Optional[int] = None,
        trip_id: Optional[int] = None, stop_id: Optional[int] = None, from_state: Optional[str] = None,
        to_state: Optional[str] = None, lat: Optional[float] = None, lng: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None) -> AuditEvent:
    ev = AuditEvent(
        rescue_id=rescue_id, trip_id=trip_id, stop_id=stop_id, entity=entity, action=action,
        from_state=from_state, to_state=to_state, actor_user_id=actor.id if actor else None,
        actor_role=actor.role if actor else "system", at=clock.now(), lat=lat, lng=lng, details=details or {},
    )
    db.add(ev)
    return ev


def event_json(e: AuditEvent) -> Dict[str, Any]:
    return {
        "id": e.id, "at": e.at.isoformat() + "Z", "entity": e.entity, "action": e.action,
        "from_state": e.from_state, "to_state": e.to_state, "actor_user_id": e.actor_user_id,
        "actor_role": e.actor_role, "trip_id": e.trip_id, "stop_id": e.stop_id,
        "location": {"lat": e.lat, "lng": e.lng} if e.lat is not None else None, "details": e.details,
    }
