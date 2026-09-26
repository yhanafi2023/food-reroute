"""Community-need (Census poverty) data for the map layer and organization cards.

See app/community_need.py for the data and app/intelligence/allocation.py for how
this becomes one weighted factor in matching (never a hard constraint).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import community_need
from app.auth import get_current_user
from app.db import get_db
from app.eligibility import meals_committed_today
from app.models import Organization, User

router = APIRouter(prefix="/community-need", tags=["community-need"])


@router.get("/areas")
def areas(user: User = Depends(get_current_user)):
    return {
        "source": community_need.source(), "disclaimer": community_need.DISCLAIMER,
        "legend": community_need.bucket_legend(), "areas": community_need.areas(),
    }


@router.get("/organizations/{organization_id}")
def organization_need(organization_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    need = community_need.score_for(org.lat, org.lng)
    p = org.receiver_profile
    requested = meals_committed_today(db, org.id) if p else 0
    fresh_need = bool(p and p.current_need is not None)
    return {
        "organization_id": org.id, "name": org.name,
        "community_need": need,  # None when the organization falls outside every loaded tract
        "disclaimer": community_need.DISCLAIMER,
        "requested_food": {
            "meals_committed_today": requested,
            "current_need": p.current_need if fresh_need else None,
            "typical_nightly_need": p.typical_nightly_need if p else None,
        },
    }
