"""Over-prep insights from the restaurant's own donation history.

Surplus = quantities the restaurant posted, per menu item, by local weekday. Nothing is
suggested until there are at least 4 weeks of history. Suggestions describe patterns in
their data, not guarantees.

Weekday pattern: over the last (up to) 10 occurrences of a weekday since the first post,
if an item was surplus on at least 60% of them and at least 4 times, suggest preparing less.

Savings after 'tried it':
  baseline = average surplus per week for the item over the 4 weeks before tried_at
  current  = average surplus per week for the item over the full weeks since tried_at
  estimated_food_cost_saved = (baseline - current) x cost_per_unit
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from app import clock
from app.models import DonationItem, MenuItem, Organization, PrepChange, Rescue
from app.value.common import cost_per_unit, local

MIN_HISTORY_DAYS = 28
LOOKBACK_OCCURRENCES = 10
MIN_SHARE, MIN_COUNT = 0.6, 4
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
PREDICTION_SERVICE_URL = os.getenv("PREDICTION_SERVICE_URL", "").rstrip("/")
CAVEAT = "A pattern in your own donation records, not a guarantee. Season, menu changes and events also matter."


def history(db: Session, org_id: int) -> Dict[int, Dict[date, float]]:
    """{menu_item_id: {local_date: quantity posted}} for non-draft posts (cancelled posts excluded)."""
    profile = db.get(Organization, org_id).restaurant_profile
    out: Dict[int, Dict[date, float]] = defaultdict(lambda: defaultdict(float))
    rows = (db.query(DonationItem, Rescue).join(Rescue, Rescue.id == DonationItem.rescue_id)
            .filter(Rescue.restaurant_org_id == org_id, Rescue.is_draft.is_(False), Rescue.status != "cancelled",
                    DonationItem.menu_item_id.isnot(None)).all())
    for item, rescue in rows:
        out[item.menu_item_id][local(rescue.created_at, profile).date()] += item.quantity
    return out


def first_post_date(db: Session, org_id: int) -> Optional[date]:
    profile = db.get(Organization, org_id).restaurant_profile
    r = (db.query(Rescue).filter(Rescue.restaurant_org_id == org_id, Rescue.is_draft.is_(False))
         .order_by(Rescue.created_at).first())
    return local(r.created_at, profile).date() if r else None


def weekday_patterns(db: Session, org_id: int, today: Optional[date] = None) -> List[Dict[str, Any]]:
    profile = db.get(Organization, org_id).restaurant_profile
    today = today or local(clock.now(), profile).date()
    first = first_post_date(db, org_id)
    if first is None or (today - first).days < MIN_HISTORY_DAYS:
        return []
    cards = []
    for menu_id, by_day in history(db, org_id).items():
        menu = db.get(MenuItem, menu_id)
        if menu is None:
            continue
        for wd in range(7):
            days = []
            d = today - timedelta(days=1)
            while len(days) < LOOKBACK_OCCURRENCES and d >= first:
                if d.weekday() == wd:
                    days.append(d)
                d -= timedelta(days=1)
            if len(days) < MIN_COUNT:
                continue
            hits = [by_day[x] for x in days if by_day.get(x, 0) > 0]
            if len(hits) >= MIN_COUNT and len(hits) / len(days) >= MIN_SHARE:
                avg = sum(hits) / len(hits)
                unit = menu.unit.replace("_", " ") + ("s" if round(avg, 1) != 1 else "")
                card = {
                    "menu_item_id": menu.id, "item": menu.name, "weekday": wd, "weekday_name": DAY_NAMES[wd],
                    "surplus_days": len(hits), "days_checked": len(days), "average_surplus": round(avg, 1), "unit": menu.unit,
                    "text": f"{menu.name}: surplus on {len(hits)} of the last {len(days)} {DAY_NAMES[wd]}s, averaging "
                            f"{avg:.1f} {unit}. Consider preparing less on {DAY_NAMES[wd]}s.",
                    "caveat": CAVEAT,
                }
                if menu.typical_batch_size:
                    card["share_of_batch_unsold"] = round(avg / menu.typical_batch_size, 3)
                    card["share_note"] = f"about {avg / menu.typical_batch_size:.0%} of your usual batch of {menu.typical_batch_size:g}"
                cards.append(card)
    return sorted(cards, key=lambda c: (-c["surplus_days"] / c["days_checked"], -c["average_surplus"]))


def trend(db: Session, org_id: int, today: Optional[date] = None) -> List[Dict[str, Any]]:
    profile = db.get(Organization, org_id).restaurant_profile
    today = today or local(clock.now(), profile).date()
    out = []
    for menu_id, by_day in history(db, org_id).items():
        last4 = sum(q for d, q in by_day.items() if today - timedelta(days=28) <= d < today)
        prev4 = sum(q for d, q in by_day.items() if today - timedelta(days=56) <= d < today - timedelta(days=28))
        menu = db.get(MenuItem, menu_id)
        out.append({"menu_item_id": menu_id, "item": menu.name if menu else str(menu_id), "unit": menu.unit if menu else "",
                    "last_4_weeks_per_week": round(last4 / 4, 2), "previous_4_weeks_per_week": round(prev4 / 4, 2)})
    return out


def savings(db: Session, org_id: int, today: Optional[date] = None) -> List[Dict[str, Any]]:
    """Estimated food cost saved for each 'tried it' change with enough data and a cost."""
    profile = db.get(Organization, org_id).restaurant_profile
    today = today or local(clock.now(), profile).date()
    hist = history(db, org_id)
    out = []
    for ch in db.query(PrepChange).filter_by(organization_id=org_id).order_by(PrepChange.tried_at).all():
        menu = db.get(MenuItem, ch.menu_item_id)
        tried = local(ch.tried_at, profile).date()
        weeks_after = (today - tried).days // 7
        by_day = hist.get(ch.menu_item_id, {})
        baseline = sum(q for d, q in by_day.items() if tried - timedelta(days=28) <= d < tried) / 4
        current = (sum(q for d, q in by_day.items() if tried <= d < tried + timedelta(days=7 * weeks_after)) / weeks_after
                   if weeks_after >= 1 else None)
        cost = cost_per_unit(menu) if menu else None
        entry = {"menu_item_id": ch.menu_item_id, "item": menu.name if menu else "", "unit": menu.unit if menu else "",
                 "tried_at": tried.isoformat(), "weekday": DAY_NAMES[ch.weekday] if ch.weekday is not None else None,
                 "baseline_per_week": round(baseline, 2), "current_per_week": round(current, 2) if current is not None else None,
                 "weeks_after": weeks_after, "cost_per_unit": cost,
                 "formula": "estimated_food_cost_saved per week = (baseline_surplus - current_surplus) x cost_per_unit",
                 "caveat": "Estimated. Other factors (season, menu changes) also affect surplus."}
        if current is None:
            entry.update(estimated_food_cost_saved_per_week=None, note="Needs at least one full week after 'tried it'")
        elif cost is None:
            entry.update(estimated_food_cost_saved_per_week=None, note="Add this item's food cost to see savings")
        else:
            entry.update(estimated_food_cost_saved_per_week=round((baseline - current) * cost, 2), note="")
        out.append(entry)
    return out


def forecast(db: Session, org_id: int) -> Dict[str, Any]:
    """Tomorrow's surplus per item from the Role 4 prediction service, if one is configured."""
    if not PREDICTION_SERVICE_URL:
        return {"available": False, "items": [],
                "note": "No prediction service is configured. FoodFlow does not show forecasts from synthetic models."}
    items = [{"menu_item_id": m.id, "name": m.name, "unit": m.unit}
             for m in db.query(MenuItem).filter_by(organization_id=org_id, active=True)]
    try:
        r = httpx.post(f"{PREDICTION_SERVICE_URL}/surplus-forecast", json={"restaurant_id": org_id, "items": items}, timeout=3)
        r.raise_for_status()
        data = r.json()
        return {"available": True, "items": data.get("items", []), "source": data.get("source", PREDICTION_SERVICE_URL),
                "note": "From the prediction service; see its source label."}
    except Exception as e:
        return {"available": False, "items": [], "note": f"Prediction service unavailable: {str(e)[:120]}"}


def tried(db: Session, org_id: int, menu_item_id: int, weekday: Optional[int], user_id: int, note: str = "") -> PrepChange:
    ch = PrepChange(organization_id=org_id, menu_item_id=menu_item_id, weekday=weekday, tried_at=clock.now(),
                    note=note, created_by=user_id)
    db.add(ch)
    db.flush()
    return ch

