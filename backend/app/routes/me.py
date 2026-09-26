"""Per-user notification preferences and the user's own notifications (section 8)."""
from typing import List, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import notify
from app.auth import get_current_user
from app.db import get_db
from app.models import Notification, User

router = APIRouter(prefix="/me", tags=["notifications"])


class Prefs(BaseModel):
    channels: List[Literal["console", "email", "sms"]] = ["console", "email"]
    muted: List[str] = []


@router.get("/notification-preferences")
def get_prefs(user: User = Depends(get_current_user)):
    p = user.notification_prefs or {}
    return {"channels": p.get("channels", ["console", "email"]), "muted": p.get("muted", []),
            "available_channels": notify.available_channels(), "events": list(notify.EVENTS)}


@router.put("/notification-preferences")
def put_prefs(body: Prefs, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    unknown = [e for e in body.muted if e not in notify.EVENTS]
    if unknown:
        from fastapi import HTTPException
        raise HTTPException(422, f"Unknown events: {', '.join(unknown)}")
    user.notification_prefs = {"channels": body.channels, "muted": body.muted}
    db.commit()
    return get_prefs(user)


@router.get("/notifications")
def my_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Notification).filter_by(user_id=user.id).order_by(Notification.id.desc()).limit(100).all()
    return [notify.notification_json(n) for n in rows]
