"""Opt-in marketing: public partner page data, a 1080x1080 monthly social card, a QR window decal.
Nothing is public unless the restaurant opts in. Receiving orgs are named only with their consent.
People served are never shown."""
from __future__ import annotations

import io
from typing import Any, Dict

import qrcode
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from app.assumptions import LBS_PER_MEAL
from app.config import FRONTEND_URL
from app.models import Organization, Rescue, Trip, TripStop


def partner_page(db: Session, org: Organization) -> Dict[str, Any]:
    stops = (db.query(TripStop).join(Trip, Trip.id == TripStop.trip_id).join(Rescue, Rescue.id == Trip.rescue_id)
             .filter(Rescue.restaurant_org_id == org.id, TripStop.status == "received").all())
    meals = sum(s.received_meals or 0 for s in stops)
    named = sorted({s.organization.name for s in stops
                    if s.organization.receiver_profile and s.organization.receiver_profile.public_naming_consent})
    others = len({s.organization_id for s in stops}) - len(named)
    return {"name": org.name, "badge": "Food Rescue Partner", "meals_donated_to_date": meals,
            "pounds_diverted_to_date": round(meals * LBS_PER_MEAL, 1), "pounds_method": "meals x 1.2 lbs (Feeding America)",
            "partner_organizations": named, "other_partner_organizations": others,
            "is_fictional": org.is_fictional}


def partner_url(org: Organization) -> str:
    return f"{FRONTEND_URL}/partners/{org.public_slug}"


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def social_card_png(org_name: str, month_label: str, meals: int, fictional: bool) -> bytes:
    img = Image.new("RGB", (1080, 1080), (20, 86, 217))
    d = ImageDraw.Draw(img)
    d.text((80, 90), "FOOD RESCUE PARTNER", fill=(219, 230, 251), font=_font(40))
    d.text((80, 190), org_name, fill=(255, 255, 255), font=_font(64))
    d.text((80, 360), f"{meals:,}", fill=(255, 255, 255), font=_font(220))
    lines = [f"meals shared with neighbors in need", f"in {month_label},", "instead of throwing them away."]
    for i, t in enumerate(lines):
        d.text((80, 640 + i * 70), t, fill=(255, 255, 255), font=_font(52))
    d.text((80, 960), "FoodFlow" + ("  |  FICTIONAL DEMO DATA" if fictional else ""), fill=(219, 230, 251), font=_font(34))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def decal_qr_png(url: str) -> bytes:
    img = qrcode.make(url, box_size=12, border=4)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
