from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.config import TIMEZONE
from app.models import RestaurantProfile


def tz_for(profile: RestaurantProfile) -> ZoneInfo:
    return ZoneInfo(profile.timezone or TIMEZONE)


def local(dt_utc: datetime, profile: RestaurantProfile) -> datetime:
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(tz_for(profile)).replace(tzinfo=None)


def to_utc(dt_local: datetime, profile: RestaurantProfile) -> datetime:
    return dt_local.replace(tzinfo=tz_for(profile)).astimezone(timezone.utc).replace(tzinfo=None)


def cost_per_unit(menu) -> float | None:
    """The restaurant's own food cost for one unit: actual cost, else price x food cost %."""
    if menu.actual_cost_per_unit is not None:
        return float(menu.actual_cost_per_unit)
    if menu.food_cost_pct is not None:
        return round(menu.menu_price_per_unit * menu.food_cost_pct / 100, 4)
    return None
