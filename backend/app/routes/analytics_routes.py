"""Analytics (section 11)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import analytics
from app.auth import ADMIN
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/coverage")
def coverage(include_fictional: bool = True, user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    return analytics.coverage(db, include_fictional)


@router.get("/compare-fleets")
def compare_fleets(user: User = Depends(ADMIN)):
    """Runs the seeded simulation twice (volunteer-only, mixed fleet). Deterministic; cached after the first run."""
    return analytics.compare_fleets()


@router.get("/matching-rejections")
def matching_rejections(user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    return analytics.matching_rejections(db)
