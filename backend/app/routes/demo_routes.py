"""Demo controls: persona sign-in, clock, reset. Only mounted when DEMO_MODE=true; fictional data only."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import demo
from app.auth import create_token, user_json
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/demo", tags=["demo"])


class SigninIn(BaseModel):
    persona: Literal["restaurant", "volunteer", "org", "coordinator"]


class ClockIn(BaseModel):
    action: Literal["play", "pause", "advance", "restart"]
    minutes: float = Field(default=0, ge=0, le=24 * 60)
    rate: Optional[float] = Field(default=None, gt=0, le=120)


@router.get("/state")
def get_state():
    return demo.state()


@router.post("/signin")
def signin(body: SigninIn, db: Session = Depends(get_db)):
    """One-click sign-in as a fictional demo account (no code needed; DEMO_MODE only)."""
    user = db.query(User).filter_by(email=demo.PERSONAS[body.persona]["email"], is_demo_account=True).first()
    if user is None:
        raise HTTPException(404, "Demo accounts are missing; reset the demo")
    return {"token": create_token(user), "user": user_json(user)}


@router.post("/clock")
def set_clock(body: ClockIn):
    d = demo.current()
    if d is None:
        raise HTTPException(409, "The demo is using the real clock (DEMO_CLOCK_START=real)")
    if body.action == "pause":
        d.pause()
    elif body.action == "play":
        d.play(body.rate)
    elif body.action == "advance":
        d.advance(minutes=body.minutes)
        from app.jobs import run_jobs_now
        run_jobs_now()
    else:
        d.restart()
    return demo.state()


@router.post("/reset")
def reset():
    return demo.reset()
