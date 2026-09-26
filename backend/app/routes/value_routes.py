"""Restaurant value module: zero-effort posting, over-prep insights, monthly value report, marketing."""
import statistics
from datetime import date
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import audit, clock
from app.auth import ADMIN, ORG_MANAGER, RESTAURANT_ANY, RESTAURANT_MANAGER
from app.db import get_db
from app.models import MenuItem, Organization, ReceiverProfile, Rescue, RescueTemplate, ToteLedger, User
from app.value import insights, marketing, report
from app.value.common import local

router = APIRouter(tags=["restaurant value"])


class ValueSettingsIn(BaseModel):
    timezone: str = Field(default="", max_length=40)
    nudges_enabled: bool = True
    nudge_minutes_before: int = Field(default=30, ge=5, le=240)
    pickups_after_closing: bool = False
    hauling_cost_per_lb: Optional[float] = Field(default=None, ge=0, le=100)
    hauling_cost_per_pickup: Optional[float] = Field(default=None, ge=0, le=100000)
    container_size_yd3: Optional[float] = Field(default=None, gt=0, le=100)
    hauling_pickups_per_week: Optional[float] = Field(default=None, gt=0, le=50)
    social_card_enabled: bool = False


FIELDS = list(ValueSettingsIn.model_fields)


def _settings(p) -> dict:
    return {k: getattr(p, k) for k in FIELDS} | {"public_partner_page": p.public_partner_page}


@router.get("/restaurants/me/value-settings")
def get_settings(user: User = Depends(RESTAURANT_MANAGER), db: Session = Depends(get_db)):
    return _settings(db.get(Organization, user.organization_id).restaurant_profile)


@router.put("/restaurants/me/value-settings")
def put_settings(body: ValueSettingsIn, user: User = Depends(RESTAURANT_MANAGER), db: Session = Depends(get_db)):
    if body.timezone:
        try:
            ZoneInfo(body.timezone)
        except ZoneInfoNotFoundError:
            raise HTTPException(422, "Unknown time zone; use a name like America/New_York")
    p = db.get(Organization, user.organization_id).restaurant_profile
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    audit.log(db, "value_settings_updated", entity="organization", actor=user, details=body.model_dump())
    db.commit()
    return _settings(p)


@router.post("/restaurants/me/templates/from-menu")
def templates_from_menu(user: User = Depends(RESTAURANT_ANY), db: Session = Depends(get_db)):
    """One template per active menu item (quantity 1 of its unit), for one-tap posting."""
    made = []
    existing = {t.name for t in db.query(RescueTemplate).filter_by(organization_id=user.organization_id)}
    for m in db.query(MenuItem).filter_by(organization_id=user.organization_id, active=True).order_by(MenuItem.name):
        if m.name in existing:
            continue
        unit = {"meal": "individual_meal"}.get(m.unit, m.unit)
        t = RescueTemplate(organization_id=user.organization_id, name=m.name, created_by=user.id, created_at=clock.now(),
                           fields={"quantity": 1, "unit": unit, "category": m.category, "menu_item_id": m.id,
                                   "description": m.name, "allergens": m.allergens or [], "dietary_tags": []})
        db.add(t)
        made.append(m.name)
    db.commit()
    return {"created": made}


@router.get("/restaurants/me/post-timing")
def post_timing(user: User = Depends(RESTAURANT_ANY), db: Session = Depends(get_db)):
    """Median seconds from opening the post form to submitting it, from recorded posts."""
    vals = [r.post_duration_seconds for r in db.query(Rescue).filter(Rescue.restaurant_org_id == user.organization_id,
                                                                       Rescue.post_duration_seconds.isnot(None))]
    return {"posts_timed": len(vals), "median_seconds": statistics.median(vals) if vals else None,
            "note": "Measured by the app from form open to submit" if vals else "No timed posts yet"}


# ---------- insights ----------

@router.get("/restaurants/me/insights")
def my_insights(user: User = Depends(RESTAURANT_ANY), db: Session = Depends(get_db)):
    first = insights.first_post_date(db, user.organization_id)
    today = local(clock.now(), db.get(Organization, user.organization_id).restaurant_profile).date()
    days = (today - first).days if first else 0
    return {"history_days": days, "min_history_days": insights.MIN_HISTORY_DAYS,
            "suggestions": insights.weekday_patterns(db, user.organization_id),
            "suggestions_note": None if days >= insights.MIN_HISTORY_DAYS else
            f"Suggestions start after {insights.MIN_HISTORY_DAYS} days of history ({days} so far).",
            "trend": insights.trend(db, user.organization_id), "savings": insights.savings(db, user.organization_id),
            "forecast": insights.forecast(db, user.organization_id), "caveat": insights.CAVEAT}


class TriedIn(BaseModel):
    menu_item_id: int
    weekday: Optional[int] = Field(default=None, ge=0, le=6)
    note: str = Field(default="", max_length=300)


@router.post("/restaurants/me/insights/tried")
def tried_it(body: TriedIn, user: User = Depends(RESTAURANT_ANY), db: Session = Depends(get_db)):
    m = db.get(MenuItem, body.menu_item_id)
    if m is None or m.organization_id != user.organization_id:
        raise HTTPException(404, "Menu item not found")
    ch = insights.tried(db, user.organization_id, m.id, body.weekday, user.id, body.note)
    audit.log(db, "prep_change_tried", entity="organization", actor=user, details={"menu_item_id": m.id, "weekday": body.weekday})
    db.commit()
    return {"id": ch.id, "menu_item_id": m.id, "tried_at": ch.tried_at.isoformat() + "Z"}


# ---------- monthly report ----------

@router.get("/restaurants/me/value-report")
def value_report(month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), format: str = Query("json", pattern="^(json|pdf)$"),
                 user: User = Depends(RESTAURANT_MANAGER), db: Session = Depends(get_db)):
    r = report.build(db, user.organization_id, month)
    if format == "json":
        return r
    return Response(report.render_pdf(r), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="what-you-got-back-{month}.pdf"'})


# ---------- totes ----------

@router.get("/restaurants/me/totes")
def my_totes(user: User = Depends(RESTAURANT_ANY), db: Session = Depends(get_db)):
    p = db.get(Organization, user.organization_id).restaurant_profile
    ledger = db.query(ToteLedger).filter_by(organization_id=user.organization_id).order_by(ToteLedger.id).all()
    return {"on_hand": p.totes_on_hand, "out_on_trips": p.totes_out,
            "ledger": [{"at": l.at.isoformat() + "Z", "change": l.change, "reason": l.reason, "trip_id": l.trip_id} for l in ledger]}


@router.post("/admin/restaurants/{org_id}/totes/lend")
def lend_totes(org_id: int, count: int = Body(..., embed=True, ge=1, le=500), user: User = Depends(ADMIN),
               db: Session = Depends(get_db)):
    org = db.get(Organization, org_id)
    if org is None or org.kind != "restaurant":
        raise HTTPException(404, "Restaurant not found")
    org.restaurant_profile.totes_on_hand += count
    db.add(ToteLedger(organization_id=org_id, change=count, reason="lent", actor_user_id=user.id, at=clock.now()))
    db.commit()
    return {"on_hand": org.restaurant_profile.totes_on_hand}


# ---------- marketing (opt-in) ----------

def _month_meals(db: Session, org_id: int, month: str) -> int:
    return report.build(db, org_id, month)["lines"]["community_impact"]["meals_donated"]


def _month_label(month: str) -> str:
    y, m = map(int, month.split("-"))
    return date(y, m, 1).strftime("%B %Y")


@router.get("/restaurants/me/social-card")
def social_card_preview(month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), user: User = Depends(RESTAURANT_MANAGER),
                        db: Session = Depends(get_db)):
    org = db.get(Organization, user.organization_id)
    if not org.restaurant_profile.social_card_enabled:
        raise HTTPException(403, "Social cards are off. Turn them on in value settings.")
    meals = _month_meals(db, org.id, month)
    return {"month": month, "meals": meals, "approved": month in (org.restaurant_profile.approved_social_cards or []),
            "text": f"This month we shared {meals:,} meals with neighbors in need instead of throwing them away.",
            "note": "Approve before download."}


@router.post("/restaurants/me/social-card/approve")
def approve_social_card(month: str = Body(..., embed=True, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
                        user: User = Depends(RESTAURANT_MANAGER), db: Session = Depends(get_db)):
    p = db.get(Organization, user.organization_id).restaurant_profile
    if not p.social_card_enabled:
        raise HTTPException(403, "Social cards are off. Turn them on in value settings.")
    p.approved_social_cards = sorted(set(p.approved_social_cards or []) | {month})
    audit.log(db, "social_card_approved", entity="organization", actor=user, details={"month": month})
    db.commit()
    return {"approved": p.approved_social_cards}


@router.get("/restaurants/me/social-card.png")
def social_card_png(month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), user: User = Depends(RESTAURANT_MANAGER),
                    db: Session = Depends(get_db)):
    org = db.get(Organization, user.organization_id)
    p = org.restaurant_profile
    if not p.social_card_enabled or month not in (p.approved_social_cards or []):
        raise HTTPException(403, "Turn on social cards and approve this month's card first")
    png = marketing.social_card_png(org.name, _month_label(month), _month_meals(db, org.id, month), org.is_fictional)
    return Response(png, media_type="image/png")


@router.get("/restaurants/me/decal-qr.png")
def decal_qr(user: User = Depends(RESTAURANT_MANAGER), db: Session = Depends(get_db)):
    org = db.get(Organization, user.organization_id)
    if not org.restaurant_profile.public_partner_page or not org.public_slug:
        raise HTTPException(403, "Turn on your public partner page first")
    return Response(marketing.decal_qr_png(marketing.partner_url(org)), media_type="image/png")


@router.put("/orgs/me/public-naming")
def public_naming(consent: bool = Body(..., embed=True), user: User = Depends(ORG_MANAGER), db: Session = Depends(get_db)):
    p = db.get(ReceiverProfile, user.organization_id)
    p.public_naming_consent = consent
    audit.log(db, "public_naming_consent", entity="organization", actor=user, details={"consent": consent})
    db.commit()
    return {"public_naming_consent": consent}

