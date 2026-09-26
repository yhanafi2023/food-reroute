"""Miami-Dade surplus prospect directory, the seven-day surplus log, and opportunity ranking.

Researched prospects live in backend/data/miami_prospects.json (public sources,
date checked, evidence level). They are NOT enrolled partners. Nothing here
invents quantities: a prospect is ranked only when a measured quantity exists,
either documented in a public source (with a reporting period) or from a
completed seven-day log the business reported.
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.logistics.geo import haversine_miles
from app.models import Restaurant, SurplusLog

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "miami_prospects.json"
EVIDENCE_LEVELS = ("measured", "documented_donation", "marketplace_listing", "none_found")
EVIDENCE_LABELS = {
    "measured": "Measured surplus (quantity and period documented)",
    "documented_donation": "Named donor of a food-rescue organization",
    "marketplace_listing": "Public surplus-marketplace listing found",
    "none_found": "No surplus evidence found",
}
LOG_DAYS = 7
RECOVERABLE = ("discarded", "composted")  # safe food that currently leaves the kitchen unused
ALREADY_CHANNELED = ("donated", "sold_discounted")


@lru_cache(maxsize=1)
def load() -> Dict[str, Any]:
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def reference_point() -> Dict[str, Any]:
    return load()["reference_point"]


def all_prospects() -> List[Dict[str, Any]]:
    ref = reference_point()
    out = []
    for p in load()["prospects"]:
        miles = haversine_miles(ref["lat"], ref["lng"], p["lat"], p["lng"])
        out.append({**p, "miles_from_fiu": round(miles, 2), "enrollment_status": "not_enrolled",
                    "evidence_label": EVIDENCE_LABELS[p["evidence_strength"]]})
    return sorted(out, key=lambda p: p["miles_from_fiu"])


def get_prospect(prospect_id: str) -> Optional[Dict[str, Any]]:
    return next((p for p in all_prospects() if p["id"] == prospect_id), None)


def filter_prospects(q: str = "", neighborhood: str = "", business_type: str = "",
                     evidence: Iterable[str] = (), max_miles: Optional[float] = None) -> List[Dict[str, Any]]:
    q = q.strip().lower()
    evidence = {e for e in evidence if e}
    result = []
    for p in all_prospects():
        haystack = " ".join([p["name"], p["address"], p["business_type"], p["neighborhood"]]).lower()
        if q and q not in haystack:
            continue
        if neighborhood and p["neighborhood"] != neighborhood:
            continue
        if business_type and p["business_type"] != business_type:
            continue
        if evidence and p["evidence_strength"] not in evidence:
            continue
        if max_miles is not None and p["miles_from_fiu"] > max_miles:
            continue
        result.append(p)
    return result


def facets() -> Dict[str, Any]:
    ps = all_prospects()
    return {
        "neighborhoods": sorted({p["neighborhood"] for p in ps}),
        "business_types": sorted({p["business_type"] for p in ps}),
        "evidence_levels": [{"value": v, "label": EVIDENCE_LABELS[v]} for v in EVIDENCE_LEVELS],
        "reference_point": reference_point(),
        "checked": load()["checked"],
        "about": load()["_about"],
    }


# ---------- seven-day log ----------

def log_entries(db: Session, prospect_id: Optional[str] = None, restaurant_id: Optional[int] = None) -> List[SurplusLog]:
    q = db.query(SurplusLog)
    q = q.filter_by(prospect_id=prospect_id) if prospect_id else q.filter_by(restaurant_id=restaurant_id)
    return q.order_by(SurplusLog.log_date).all()


def log_entry_json(e: SurplusLog) -> Dict[str, Any]:
    return {
        "id": e.id, "log_date": e.log_date.isoformat(), "surplus_meals": e.surplus_meals, "surplus_lbs": e.surplus_lbs,
        "safe_to_donate": e.safe_to_donate, "disposition": e.disposition, "food_categories": e.food_categories,
        "ready_time": e.ready_time, "notes": e.notes,
    }


def summarize_log(entries: List[SurplusLog]) -> Dict[str, Any]:
    """Measured figures from the first seven logged days. Self-reported."""
    days = entries[:LOG_DAYS]
    complete = len(days) == LOG_DAYS
    recoverable_days = [e for e in days if e.safe_to_donate and e.disposition in RECOVERABLE and e.surplus_meals > 0]
    channeled = sum(e.surplus_meals for e in days if e.disposition in ALREADY_CHANNELED)
    recoverable = sum(e.surplus_meals for e in recoverable_days)
    ready_times = sorted({e.ready_time for e in recoverable_days if e.ready_time})
    return {
        "days_logged": len(entries),
        "days_needed": LOG_DAYS,
        "complete": complete,
        "period_start": days[0].log_date.isoformat() if days else None,
        "period_end": days[-1].log_date.isoformat() if days else None,
        "total_surplus_meals": sum(e.surplus_meals for e in days),
        "total_surplus_lbs": round(sum(e.surplus_lbs for e in days), 1),
        "recoverable_meals": recoverable,
        "recoverable_days": len(recoverable_days),
        "already_channeled_meals": channeled,
        "typical_ready_times": ready_times,
        "basis": "Self-reported seven-day kitchen surplus log" if complete else "Log in progress: not yet a measurement",
    }


def upsert_entry(db: Session, body: Dict[str, Any], user_id: int, prospect_id: Optional[str] = None,
                 restaurant_id: Optional[int] = None) -> SurplusLog:
    log_date: date = body["log_date"]
    q = db.query(SurplusLog).filter_by(log_date=log_date)
    q = q.filter_by(prospect_id=prospect_id) if prospect_id else q.filter_by(restaurant_id=restaurant_id)
    entry = q.one_or_none() or SurplusLog(prospect_id=prospect_id, restaurant_id=restaurant_id, log_date=log_date)
    for key in ("surplus_meals", "surplus_lbs", "safe_to_donate", "disposition", "food_categories", "ready_time", "notes"):
        setattr(entry, key, body[key])
    entry.reported_by = user_id
    db.add(entry)
    db.commit()
    return entry


# ---------- ranking ----------

def _documented_weekly(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A public, business-specific measurement converted to meals per week, if one exists."""
    m = p.get("surplus_measurement")
    if not m or m.get("meals") is None or not m.get("period_days"):
        return None
    return {"weekly_meals": m["meals"] * 7 / m["period_days"], "pickups_per_week": m.get("pickups_per_week"),
            "basis": f"Documented: {m.get('source', 'source listed')} ({m.get('period', 'period listed')})"}


def opportunity(name: str, summary: Optional[Dict[str, Any]], documented: Optional[Dict[str, Any]],
                commitments: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if summary and summary["complete"]:
        weekly, pickups, basis = summary["recoverable_meals"], summary["recoverable_days"], (
            f"{summary['basis']}, {summary['period_start']} to {summary['period_end']}")
        channeled = summary["already_channeled_meals"]
    elif documented:
        weekly, pickups, basis, channeled = documented["weekly_meals"], documented["pickups_per_week"], documented["basis"], 0
    else:
        return None
    return {
        "name": name,
        "recoverable_meals_per_week": round(weekly, 1),
        "pickups_per_week": pickups,
        "meals_per_pickup": round(weekly / pickups, 1) if pickups else None,
        "already_channeled_meals_per_week": channeled,
        "existing_commitments": [c["program"] for c in commitments],
        "basis": basis,
    }


def rank_opportunities(db: Session) -> Dict[str, Any]:
    """Rank only measured opportunities. Order: meals not already covered by another program first,
    then recoverable meals per week, then fewer pickups needed per meal (bigger, less frequent pickups)."""
    ranked, not_ranked = [], []
    for p in all_prospects():
        summary = summarize_log(log_entries(db, prospect_id=p["id"]))
        opp = opportunity(p["name"], summary if summary["days_logged"] else None, _documented_weekly(p),
                          p["existing_commitments"])
        if opp is None or opp["recoverable_meals_per_week"] <= 0:
            reason = ("No measured surplus. Start the seven-day log." if summary["days_logged"] == 0
                      else f"Seven-day log in progress ({summary['days_logged']} of {LOG_DAYS} days)."
                      if not summary["complete"] else "Log complete: no recoverable surplus recorded.")
            not_ranked.append({"id": p["id"], "name": p["name"], "kind": "prospect", "reason": reason,
                               "evidence_strength": p["evidence_strength"], "miles_from_fiu": p["miles_from_fiu"]})
            continue
        ranked.append({**opp, "id": p["id"], "kind": "prospect", "miles_from_fiu": p["miles_from_fiu"],
                       "is_demo": False})
    ref = reference_point()
    for r in db.query(Restaurant).all():
        summary = summarize_log(log_entries(db, restaurant_id=r.id))
        if not summary["complete"]:
            continue
        opp = opportunity(r.name, summary, None, [])
        if opp and opp["recoverable_meals_per_week"] > 0:
            ranked.append({**opp, "id": f"restaurant-{r.id}", "kind": "enrolled_partner", "is_demo": r.is_demo_seed,
                           "miles_from_fiu": round(haversine_miles(ref["lat"], ref["lng"], r.lat, r.lng), 2)})
    ranked.sort(key=lambda o: (bool(o["existing_commitments"]), -o["recoverable_meals_per_week"],
                               o["pickups_per_week"] or 99))
    for i, o in enumerate(ranked, start=1):
        o["rank"] = i
    return {"ranked": ranked, "not_ranked": not_ranked,
            "method": "Ranked only with measured recoverable surplus (safe food that would be discarded or composted), "
                      "pickup frequency (days per week with recoverable surplus), and existing donation or resale "
                      "commitments (businesses already served by another program rank after those that are not)."}
