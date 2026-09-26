"""Demo controls: clock and reset. Only mounted when DEMO_MODE=true; fictional data only.

Sign-in is unchanged: demo accounts sign in through /auth/request-code and /auth/verify like everyone else.
Changing the clock or resetting requires an admin.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import demo
from app.auth import ADMIN
from app.models import User

router = APIRouter(prefix="/demo", tags=["demo"])


class ClockIn(BaseModel):
    action: Literal["play", "pause", "advance", "restart"]
    minutes: float = Field(default=0, ge=0, le=24 * 60)
    rate: Optional[float] = Field(default=None, gt=0, le=120)


@router.get("/state")
def get_state():
    return demo.state()


@router.post("/clock")
def set_clock(body: ClockIn, _admin: User = Depends(ADMIN)):
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
def reset(_admin: User = Depends(ADMIN)):
    return demo.reset()
