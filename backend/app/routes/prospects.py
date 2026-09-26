"""Researched Miami-Dade prospects (not partners), the seven-day surplus log, and ranking."""
from datetime import date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app import prospects
from app.auth import require_role, restaurant_of
from app.db import get_db
from app.models import SurplusLog, User

router = APIRouter(tags=["prospects"])


class LogEntryIn(BaseModel):
    log_date: date
    surplus_meals: int = Field(ge=0, le=5000)
    surplus_lbs: float = Field(default=0, ge=0, le=10000)
    safe_to_donate: bool = False
    disposition: Literal["discarded", "composted", "donated", "sold_discounted", "staff_meal", "no_surplus"]
    food_categories: str = Field(default="", max_length=200)
    ready_time: str = Field(default="", max_length=20)
    notes: str = Field(default="", max_length=1000)

    @field_validator("log_date")
    @classmethod
    def _not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("cannot log a day that has not happened yet")
        return v

    @field_validator("disposition")
    @classmethod
    def _consistent(cls, v: str, info) -> str:
        meals = info.data.get("surplus_meals", 0)
        if v == "no_surplus" and meals:
            raise ValueError("choose what happened to the surplus, or set meals to 0")
        if v != "no_surplus" and meals == 0:
            raise ValueError("enter the number of surplus meals, or choose 'no surplus'")
        return v


def _log_payload(db: Session, prospect_id: Optional[str] = None, restaurant_id: Optional[int] = None):
    entries = prospects.log_entries(db, prospect_id=prospect_id, restaurant_id=restaurant_id)
    return {"entries": [prospects.log_entry_json(e) for e in entries], "summary": prospects.summarize_log(entries)}


@router.get("/prospects/meta")
def prospects_meta(user: User = Depends(require_role("ADMIN"))):
    return prospects.facets()


@router.get("/prospects")
def list_prospects(q: str = "", neighborhood: str = "", business_type: str = "",
                   evidence: List[str] = Query(default=[]), max_miles: Optional[float] = Query(default=None, gt=0),
                   user: User = Depends(require_role("ADMIN")), db: Session = Depends(get_db)):
    items = prospects.filter_prospects(q, neighborhood, business_type, evidence, max_miles)
    for p in items:
        p["log_summary"] = prospects.summarize_log(prospects.log_entries(db, prospect_id=p["id"]))
    return {"items": items, "total": len(prospects.all_prospects())}


@router.get("/prospects/opportunities")
def opportunities(user: User = Depends(require_role("ADMIN")), db: Session = Depends(get_db)):
    return prospects.rank_opportunities(db)


@router.get("/prospects/{prospect_id}")
def get_prospect(prospect_id: str, user: User = Depends(require_role("ADMIN")), db: Session = Depends(get_db)):
    p = prospects.get_prospect(prospect_id)
    if p is None:
        raise HTTPException(404, "Prospect not found")
    return {**p, "log": _log_payload(db, prospect_id=prospect_id)}


@router.put("/prospects/{prospect_id}/surplus-log")
def log_prospect_day(prospect_id: str, body: LogEntryIn, user: User = Depends(require_role("ADMIN")),
                     db: Session = Depends(get_db)):
    if prospects.get_prospect(prospect_id) is None:
        raise HTTPException(404, "Prospect not found")
    prospects.upsert_entry(db, body.model_dump(), user.id, prospect_id=prospect_id)
    return _log_payload(db, prospect_id=prospect_id)


@router.delete("/prospects/{prospect_id}/surplus-log/{entry_id}")
def delete_prospect_day(prospect_id: str, entry_id: int, user: User = Depends(require_role("ADMIN")),
                        db: Session = Depends(get_db)):
    entry = db.get(SurplusLog, entry_id)
    if entry is None or entry.prospect_id != prospect_id:
        raise HTTPException(404, "Log entry not found")
    db.delete(entry)
    db.commit()
    return _log_payload(db, prospect_id=prospect_id)


@router.get("/restaurants/me/surplus-log")
def my_log(user: User = Depends(require_role("RESTAURANT")), db: Session = Depends(get_db)):
    return _log_payload(db, restaurant_id=restaurant_of(db, user).id)


@router.put("/restaurants/me/surplus-log")
def log_my_day(body: LogEntryIn, user: User = Depends(require_role("RESTAURANT")), db: Session = Depends(get_db)):
    restaurant = restaurant_of(db, user)
    prospects.upsert_entry(db, body.model_dump(), user.id, restaurant_id=restaurant.id)
    return _log_payload(db, restaurant_id=restaurant.id)
