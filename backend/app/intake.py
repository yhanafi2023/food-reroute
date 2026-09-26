"""Onboarding intake: the three required questions for receiving organizations (Q1 to Q3),
plus restaurant and volunteer profiles, and the receiving-hours logic matching uses.

An organization receives no deliveries until Q1, Q2 and Q3 are all answered.
Every save appends an IntakeAnswer row (source = self_reported_by_org, who, when).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app import clock
from app.assumptions import INTAKE_CONFIRM_DAYS
from app.models import IntakeAnswer, ReceiverProfile, ReceivingException, User

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DIETARY_RULES = ("halal_only", "kosher_only", "vegetarian_only", "vegan_only", "no_pork", "no_beef")
DIETARY_TAGS = ("halal", "kosher", "vegetarian", "vegan", "contains_pork", "contains_beef", "no_pork", "no_beef")
ALLERGENS = ("peanuts", "tree_nuts", "dairy", "eggs", "gluten", "soy", "fish", "shellfish", "sesame")
RECORD_FIELDS = ("date_time", "donor_name", "donor_address", "food_description", "food_category", "quantity_meals",
                 "weight_lbs", "temperature_at_receipt", "condition", "received_by_name", "allergen_info",
                 "donor_acknowledgment")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$|^24:00$")
EIN_RE = re.compile(r"^\d{2}-\d{7}$")


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _check_windows(windows: List[List[str]]) -> List[List[str]]:
    for w in windows:
        if len(w) != 2 or not all(TIME_RE.match(t) for t in w):
            raise ValueError("each window is [\"HH:MM\", \"HH:MM\"] (24:00 allowed as an end)")
        if _minutes(w[0]) >= _minutes(w[1]):
            raise ValueError("a window must start before it ends; split overnight hours across two days")
    return windows


# ---------- Q1 to Q3 answer schemas ----------

class ExceptionIn(BaseModel):
    day: date
    reason: str = Field(default="", max_length=200)


class Q1(BaseModel):
    """When can you receive food?"""
    schedule: Dict[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"], List[List[str]]]
    exceptions: List[ExceptionIn] = []
    cutoff_minutes: int = Field(ge=0, le=720)
    receiving_contact_name: str = Field(min_length=1, max_length=120)
    receiving_contact_phone: str = Field(min_length=7, max_length=40)
    receiving_instructions: str = Field(min_length=1, max_length=1000)
    curbside_ok: bool
    curb_location: str = Field(default="", max_length=200)

    @field_validator("schedule")
    @classmethod
    def _all_days(cls, v):
        missing = [d for d in WEEKDAYS if d not in v]
        if missing:
            raise ValueError(f"give hours for every day (an empty list means closed); missing {', '.join(missing)}")
        for windows in v.values():
            _check_windows(windows)
        return v

    @model_validator(mode="after")
    def _curb(self):
        if self.curbside_ok and not self.curb_location.strip():
            raise ValueError("say where a vehicle should stop at the curb")
        return self


class Q2(BaseModel):
    """Do you take hot food? (and cold, frozen, shelf-stable, dietary and allergen rules, capacity)"""
    accepts_hot: bool
    hot_max_minutes: Optional[int] = Field(default=None, gt=0, le=240)
    can_hold_hot: Optional[bool] = None
    serves_immediately: str = Field(default="", max_length=200)
    accepts_cold: bool
    fridge_capacity_meals: Optional[int] = Field(default=None, ge=0)
    accepts_frozen: bool
    freezer_capacity_meals: Optional[int] = Field(default=None, ge=0)
    accepts_shelf_stable: bool
    dietary_rules: List[Literal[DIETARY_RULES]] = []  # type: ignore[valid-type]
    refused_allergens: List[Literal[ALLERGENS]] = []  # type: ignore[valid-type]
    max_meals_per_delivery: int = Field(gt=0, le=5000)
    typical_nightly_need: int = Field(ge=0, le=10000)

    @model_validator(mode="after")
    def _consistent(self):
        if not (self.accepts_hot or self.accepts_cold or self.accepts_frozen or self.accepts_shelf_stable):
            raise ValueError("accept at least one food category")
        if self.accepts_hot and (self.hot_max_minutes is None or self.can_hold_hot is None):
            raise ValueError("for hot food, give the longest pickup-to-arrival time you accept and whether you can hold it hot")
        if self.accepts_cold and self.fridge_capacity_meals is None:
            raise ValueError("give refrigeration capacity in meals")
        if self.accepts_frozen and self.freezer_capacity_meals is None:
            raise ValueError("give freezer capacity in meals")
        return self


class Q3(BaseModel):
    """What records do you need?"""
    required_fields: List[Literal[RECORD_FIELDS]] = Field(min_length=1)  # type: ignore[valid-type]
    report_frequency: Literal["per_delivery", "weekly", "monthly", "quarterly"]
    report_format: Literal["csv", "pdf"]
    reports_to: str = Field(default="", max_length=300)
    is_501c3: bool
    ein: Optional[str] = None

    @model_validator(mode="after")
    def _ein(self):
        if self.is_501c3 and not (self.ein and EIN_RE.match(self.ein)):
            raise ValueError("a 501(c)(3) needs an EIN in the form 12-3456789")
        return self


SCHEMAS = {"Q1": Q1, "Q2": Q2, "Q3": Q3}


def save_answers(db: Session, org_id: int, question: str, answers: BaseModel, user: Optional[User]) -> ReceiverProfile:
    profile = db.get(ReceiverProfile, org_id)
    data = answers.model_dump(mode="json")
    now = clock.now()
    if question == "Q1":
        for k in ("schedule", "cutoff_minutes", "receiving_contact_name", "receiving_contact_phone",
                  "receiving_instructions", "curbside_ok", "curb_location"):
            setattr(profile, k, data[k])
        db.query(ReceivingException).filter_by(organization_id=org_id).delete()
        for ex in answers.exceptions:  # type: ignore[attr-defined]
            db.add(ReceivingException(organization_id=org_id, day=ex.day, reason=ex.reason))
    elif question == "Q2":
        for k in data:
            setattr(profile, k, data[k])
    else:
        if data["ein"] != profile.ein:
            profile.ein_verified, profile.ein_verified_by, profile.ein_verified_at = False, None, None
        for k in ("required_fields", "report_frequency", "report_format", "reports_to", "is_501c3", "ein"):
            setattr(profile, k, data[k])
    db.add(IntakeAnswer(organization_id=org_id, question=question, answers=data, answered_by=user.id if user else None,
                        answered_at=now, confirmed_at=now))
    return profile


def latest_answers(db: Session, org_id: int) -> Dict[str, IntakeAnswer]:
    rows = db.query(IntakeAnswer).filter_by(organization_id=org_id).order_by(IntakeAnswer.answered_at, IntakeAnswer.id).all()
    return {r.question: r for r in rows}


def completeness(db: Session, org_id: int) -> Dict:
    latest = latest_answers(db, org_id)
    due_before = clock.now() - timedelta(days=INTAKE_CONFIRM_DAYS)
    questions = {}
    for q, title in (("Q1", "When can you receive food?"), ("Q2", "Do you take hot food?"),
                     ("Q3", "What records do you need?")):
        a = latest.get(q)
        questions[q] = {
            "title": title,
            "answered": a is not None,
            "answered_at": a.answered_at.isoformat() + "Z" if a else None,
            "answered_by": a.answered_by if a else None,
            "source": a.source if a else None,
            "confirmed_at": a.confirmed_at.isoformat() + "Z" if a else None,
            "confirmation_due": bool(a and a.confirmed_at < due_before),
        }
    missing = [q for q, v in questions.items() if not v["answered"]]
    return {"organization_id": org_id, "complete": not missing, "missing": missing, "questions": questions,
            "receives_deliveries": not missing,
            "confirm_every_days": INTAKE_CONFIRM_DAYS}


def is_complete(db: Session, org_id: int) -> bool:
    return len(latest_answers(db, org_id)) == 3


def confirm(db: Session, org_id: int) -> None:
    now = clock.now()
    for a in latest_answers(db, org_id).values():
        a.confirmed_at = now


# ---------- receiving hours ----------

def _local(dt_utc: datetime) -> datetime:
    return clock.to_local(dt_utc).replace(tzinfo=None)


def _day_windows(profile: ReceiverProfile, exceptions: Dict[date, str], day: date) -> List[Tuple[datetime, datetime]]:
    if day in exceptions:
        return []
    out = []
    for start, end in (profile.schedule or {}).get(WEEKDAYS[day.weekday()], []):
        s = datetime.combine(day, datetime.min.time()) + timedelta(minutes=_minutes(start))
        e = datetime.combine(day, datetime.min.time()) + timedelta(minutes=_minutes(end))
        out.append((s, e))
    return out


def _merged_windows(profile: ReceiverProfile, exceptions: Dict[date, str], around: date) -> List[Tuple[datetime, datetime]]:
    """Windows from the day before to 7 days after, merged where one ends exactly when the next starts (24/7)."""
    wins = []
    for i in range(-1, 8):
        wins.extend(_day_windows(profile, exceptions, around + timedelta(days=i)))
    wins.sort()
    merged: List[Tuple[datetime, datetime]] = []
    for s, e in wins:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _clock_text(dt_local: datetime, ref_local: datetime) -> str:
    t = dt_local.strftime("%-I:%M %p")
    if dt_local.date() == ref_local.date():
        return t
    if dt_local.date() == ref_local.date() + timedelta(days=1):
        return f"{t} tomorrow" if dt_local.hour >= 5 else t
    return f"{dt_local.strftime('%a')} {t}"


def receiving_check(db: Session, profile: ReceiverProfile, arrival_utc: datetime) -> Tuple[bool, Optional[Dict[str, str]]]:
    """Can this org receive a delivery arriving at arrival_utc? Returns (ok, reason)."""
    exceptions = {e.day: e.reason for e in db.query(ReceivingException).filter_by(organization_id=profile.organization_id)}
    t = _local(arrival_utc)
    if t.date() in exceptions:
        reason = exceptions[t.date()] or "closed that day"
        return False, {"code": "closed_exception", "text": f"closed on {t.date().isoformat()} ({reason})"}
    cutoff = timedelta(minutes=profile.cutoff_minutes or 0)
    for s, e in _merged_windows(profile, exceptions, t.date()):
        if s <= t < e:
            if t > e - cutoff:
                return False, {"code": "past_cutoff",
                               "text": f"past the last-minute cutoff: receiving ends {_clock_text(e, t)}, "
                                       f"no new deliveries after {_clock_text(e - cutoff, t)}"}
            return True, None
        if s > t:
            return False, {"code": "closed", "text": f"closed until {_clock_text(s, t)}"}
    return False, {"code": "closed", "text": "closed for the next 7 days"}


def receiving_until(db: Session, profile: ReceiverProfile, at_utc: datetime) -> Optional[datetime]:
    """Local end of the receiving window containing at_utc (for plain-English reasons)."""
    exceptions = {e.day: e.reason for e in db.query(ReceivingException).filter_by(organization_id=profile.organization_id)}
    t = _local(at_utc)
    for s, e in _merged_windows(profile, exceptions, t.date()):
        if s <= t < e:
            return e
    return None


def within_local_until(hhmm_by_day: Dict[str, str], at_utc: datetime) -> bool:
    """For restaurant 'staffed until' times. '01:00' after midnight counts for the previous evening."""
    t = _local(at_utc)
    for day_offset in (0, -1):
        d = t.date() + timedelta(days=day_offset)
        until = hhmm_by_day.get(WEEKDAYS[d.weekday()])
        if not until:
            continue
        mins = _minutes(until)
        end = datetime.combine(d, datetime.min.time()) + timedelta(minutes=mins if mins >= 5 * 60 else mins + 24 * 60)
        start = datetime.combine(d, datetime.min.time()) + timedelta(hours=5)
        if start <= t <= end:
            return True
    return False


def available_at(availability: Dict[str, List[List[str]]], at_utc: datetime, minutes: float = 0) -> bool:
    """Volunteer availability: the whole span [at, at + minutes] falls inside one window."""
    start = _local(at_utc)
    end = start + timedelta(minutes=minutes)
    for s_day in (start.date() - timedelta(days=1), start.date()):
        for s, e in availability.get(WEEKDAYS[s_day.weekday()], []):
            ws = datetime.combine(s_day, datetime.min.time()) + timedelta(minutes=_minutes(s))
            we = datetime.combine(s_day, datetime.min.time()) + timedelta(minutes=_minutes(e))
            if ws <= start and end <= we:
                return True
    return False
