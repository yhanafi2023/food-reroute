"""Notifications with pluggable providers.

console (default, dev and demo): written to the log and the notifications outbox.
email: SMTP, used when SMTP_HOST is set and the user enabled it.
sms: Twilio REST API, used only when TWILIO_* keys are set and the user enabled it.

Per-user preferences: user.notification_prefs = {"channels": ["console", "email"], "muted": ["expiry_warning"]}.
Every message goes through the outbox; a dedupe_key prevents sending the same alert twice.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Iterable, List, Optional

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import clock
from app.config import (
    SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM,
)
from app.models import Notification, User

log = logging.getLogger("foodflow.notify")

EVENTS = (
    "matched", "approaching", "vehicle_at_curb", "picked_up", "delivered", "receipt_confirmed",
    "cancelled", "reassigned", "expired", "expiry_warning", "rerouted", "intake_confirmation", "acknowledgment",
    "offer", "duplicate_warning", "draft_ready",
)


def available_channels() -> List[str]:
    chans = ["console"]
    if SMTP_HOST:
        chans.append("email")
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM:
        chans.append("sms")
    return chans


def _channels_for(user: User, event: str) -> List[str]:
    prefs = user.notification_prefs or {}
    if event in prefs.get("muted", []):
        return []
    wanted = prefs.get("channels") or ["console", "email"]
    chans = [c for c in wanted if c in available_channels()]
    return chans or ["console"]


def _deliver(n: Notification, user: Optional[User]) -> None:
    try:
        if n.channel == "console":
            log.info("[notify:%s] to=%s %s | %s", n.event, user.email if user else "-", n.subject, n.body)
        elif n.channel == "email" and user:
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = SMTP_FROM, user.email, n.subject
            msg.set_content(n.body)
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
                s.starttls()
                if SMTP_USER:
                    s.login(SMTP_USER, SMTP_PASSWORD)
                s.send_message(msg)
        elif n.channel == "sms" and user and user.phone:
            httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
                       auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                       data={"From": TWILIO_FROM, "To": user.phone, "Body": f"{n.subject}: {n.body}"[:1500]},
                       timeout=10).raise_for_status()
        else:
            n.status, n.error = "skipped", "no address for channel"
            return
        n.status, n.sent_at = "sent", clock.now()
    except Exception as e:  # a failed provider never breaks the request that triggered it
        n.status, n.error = "failed", str(e)[:300]


def send(db: Session, users: Iterable[Optional[User]], event: str, subject: str, body: str,
         dedupe: Optional[str] = None) -> List[Notification]:
    out = []
    for user in users:
        if user is None or not user.active:
            continue
        for channel in _channels_for(user, event):
            key = f"{dedupe}:{user.id}:{channel}" if dedupe else None
            if key and db.query(Notification.id).filter_by(dedupe_key=key).first():
                continue
            n = Notification(user_id=user.id, event=event, channel=channel, subject=subject, body=body,
                             dedupe_key=key, created_at=clock.now())
            try:
                with db.begin_nested():
                    db.add(n)
                    db.flush()
            except IntegrityError:
                continue
            _deliver(n, user)
            out.append(n)
    return out


def notification_json(n: Notification) -> dict:
    return {"id": n.id, "event": n.event, "channel": n.channel, "subject": n.subject, "body": n.body,
            "status": n.status, "created_at": n.created_at.isoformat() + "Z"}
