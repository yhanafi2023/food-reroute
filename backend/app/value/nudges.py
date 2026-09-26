"""Closing-time nudge: 'Any surplus tonight? Tap to repeat last post.' at each restaurant's own local
closing time minus nudge_minutes_before. Restaurants can turn it off; users can mute the event."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from sqlalchemy.orm import Session

from app import clock, notify
from app.intake import WEEKDAYS
from app.models import Organization, RestaurantProfile, User
from app.value.common import local, to_utc


def closing_today_utc(profile: RestaurantProfile, now_utc: datetime):
    t = local(now_utc, profile)
    closing = (profile.closing_times or {}).get(WEEKDAYS[t.weekday()])
    if not closing:
        return None
    hh, mm = map(int, closing.split(":"))
    close_local = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if hh < 5:  # closes after midnight: belongs to this evening
        close_local += timedelta(days=1)
    return to_utc(close_local, profile)


def send_due(db: Session) -> List[int]:
    now = clock.now()
    sent = []
    for org in db.query(Organization).filter_by(kind="restaurant").all():
        p = org.restaurant_profile
        if p is None or not p.nudges_enabled:
            continue
        close = closing_today_utc(p, now)
        if close is None:
            continue
        nudge_at = close - timedelta(minutes=p.nudge_minutes_before)
        if nudge_at <= now < close:
            users = db.query(User).filter_by(organization_id=org.id, active=True).all()
            if notify.send(db, users, "closing_nudge", "Any surplus tonight?",
                           "Tap to repeat last post, or pick a template. Pickup happens at your closing time.",
                           dedupe=f"nudge:{org.id}:{local(now, p).date().isoformat()}"):
                sent.append(org.id)
    return sent
