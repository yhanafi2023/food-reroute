"""Request bodies with validation. Responses are plain dicts shaped like the contract."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

Level = Literal["LOW", "MEDIUM", "HIGH"]


def to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _future(value: datetime) -> datetime:
    value = to_naive_utc(value)
    if value <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise ValueError("must be in the future")
    return value


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["RESTAURANT", "DRIVER", "ORGANIZATION"]
    address: Optional[str] = Field(default=None, max_length=255)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RescueIn(BaseModel):
    food_type: str = Field(min_length=1, max_length=120)
    meals: int = Field(gt=0, le=2000)
    weight_lbs: float = Field(ge=0, le=5000)
    pickup_address: Optional[str] = Field(default=None, max_length=255)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)
    pickup_deadline: datetime
    time_sensitivity: Level = "MEDIUM"
    description: str = Field(default="", max_length=1000)
    food_safety_confirmed: bool

    _deadline = field_validator("pickup_deadline")(_future)

    @field_validator("food_safety_confirmed")
    @classmethod
    def _safety(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("please confirm the food was stored and handled safely")
        return v


class NeedIn(BaseModel):
    meals_needed: int = Field(gt=0, le=5000)
    preferred_food: str = Field(default="Any", max_length=120)
    deadline: datetime
    priority: Level = "MEDIUM"

    _deadline = field_validator("deadline")(_future)


class StatusIn(BaseModel):
    status: Literal["HEADING_TO_RESTAURANT", "ARRIVED_AT_RESTAURANT", "PICKED_UP", "DELIVERING", "DELIVERED", "CONFIRMED"]


class AvailabilityIn(BaseModel):
    is_available: bool


class PredictIn(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    hour: int = Field(ge=0, le=23)
    food_category: str = "cuban"
    seats: int = Field(default=80, gt=0, le=2000)
    rain: bool = False
    local_event: bool = False
    hist_surplus_rate: float = Field(default=0.3, ge=0, le=1)

    def features(self) -> Dict[str, Any]:
        return self.model_dump()
