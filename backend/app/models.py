"""Database tables. Times are stored as naive UTC.

Index notes (see README for the Postgres/PostGIS version):
  ix_drivers_available_loc    find available drivers near a pickup (matching prefilter)
  ix_needs_status_deadline    open needs, soonest deadline first
  ix_rescues_status_deadline  open rescues by deadline (batch matching, expiry sweep)
  ix_deliveries_driver_status a driver's active delivery and history
  ix_match_stops_org          an organization's incoming deliveries (deliveries by organization)
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

ROLES = ("RESTAURANT", "DRIVER", "ORGANIZATION", "ADMIN")
RESCUE_STATUSES = ("OPEN", "MATCHED", "ACCEPTED", "PICKED_UP", "DELIVERED", "CONFIRMED", "EXPIRED", "CANCELLED")
DELIVERY_STATUSES = ("HEADING_TO_RESTAURANT", "ARRIVED_AT_RESTAURANT", "PICKED_UP", "DELIVERING", "DELIVERED", "CONFIRMED")
MATCH_STATUSES = ("PENDING", "ACCEPTED", "DECLINED", "SUPERSEDED")
LEVELS = ("LOW", "MEDIUM", "HIGH")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _in(col: str, values) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", ROLES), name="ck_users_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(255), default="")
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    food_category: Mapped[str] = mapped_column(String(40), default="cuban")
    seats: Mapped[int] = mapped_column(Integer, default=80)
    hist_surplus_rate: Mapped[float] = mapped_column(Float, default=0.3)
    is_demo_seed: Mapped[bool] = mapped_column(Boolean, default=False)  # fictional demo partner


class Driver(Base):
    __tablename__ = "drivers"
    __table_args__ = (
        CheckConstraint("capacity_meals > 0", name="ck_drivers_capacity"),
        Index("ix_drivers_available_loc", "is_available", "lat", "lng"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    capacity_meals: Mapped[int] = mapped_column(Integer, default=80)
    vehicle: Mapped[str] = mapped_column(String(60), default="Car")
    # "seed", "status" (moved when a status changed) or "gps" (shared from the driver's phone)
    location_source: Mapped[str] = mapped_column(String(10), default="seed")
    location_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    org_type: Mapped[str] = mapped_column(String(40), default="Food bank")
    address: Mapped[str] = mapped_column(String(255), default="")
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)


class FoodNeed(Base):
    __tablename__ = "food_needs"
    __table_args__ = (
        CheckConstraint("meals_needed > 0", name="ck_needs_meals"),
        CheckConstraint("meals_fulfilled >= 0", name="ck_needs_fulfilled"),
        CheckConstraint(_in("priority", LEVELS), name="ck_needs_priority"),
        CheckConstraint(_in("status", ("OPEN", "FULFILLED")), name="ck_needs_status"),
        Index("ix_needs_status_deadline", "status", "deadline"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    meals_needed: Mapped[int] = mapped_column(Integer)
    meals_fulfilled: Mapped[int] = mapped_column(Integer, default=0)
    preferred_food: Mapped[str] = mapped_column(String(120), default="Any")
    deadline: Mapped[datetime] = mapped_column(DateTime)
    priority: Mapped[str] = mapped_column(String(10), default="MEDIUM")
    status: Mapped[str] = mapped_column(String(10), default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    organization: Mapped[Organization] = relationship()


class FoodRescue(Base):
    __tablename__ = "food_rescues"
    __table_args__ = (
        CheckConstraint("meals > 0", name="ck_rescues_meals"),
        CheckConstraint("weight_lbs >= 0", name="ck_rescues_weight"),
        CheckConstraint(_in("status", RESCUE_STATUSES), name="ck_rescues_status"),
        CheckConstraint(_in("time_sensitivity", LEVELS), name="ck_rescues_sensitivity"),
        Index("ix_rescues_status_deadline", "status", "pickup_deadline"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), index=True)
    food_type: Mapped[str] = mapped_column(String(120))
    meals: Mapped[int] = mapped_column(Integer)
    weight_lbs: Mapped[float] = mapped_column(Float, default=0)
    pickup_address: Mapped[str] = mapped_column(String(255), default="")
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    pickup_deadline: Mapped[datetime] = mapped_column(DateTime)
    time_sensitivity: Mapped[str] = mapped_column(String(10), default="MEDIUM")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="OPEN")
    is_demo_seed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    restaurant: Mapped[Restaurant] = relationship()


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint(_in("status", MATCH_STATUSES), name="ck_matches_status"),
        Index("ix_matches_driver_status", "driver_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rescue_id: Mapped[int] = mapped_column(ForeignKey("food_rescues.id", ondelete="CASCADE"), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id", ondelete="CASCADE"))
    pickup_miles: Mapped[float] = mapped_column(Float)
    dropoff_miles: Mapped[float] = mapped_column(Float)
    eta_minutes: Mapped[float] = mapped_column(Float)
    eta_range_minutes: Mapped[list] = mapped_column(JSON, default=list)  # [P10, P90] from the ETA model
    pickup_eta_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eta_source: Mapped[str] = mapped_column(String(10), default="rule")
    score: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    top_candidates: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(12), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    driver: Mapped[Driver] = relationship()
    stops: Mapped[List["MatchStop"]] = relationship(
        back_populates="match", order_by="MatchStop.seq", cascade="all, delete-orphan"
    )


class MatchStop(Base):
    __tablename__ = "match_stops"
    __table_args__ = (
        CheckConstraint("meals > 0", name="ck_match_stops_meals"),
        Index("ix_match_stops_org", "organization_id", "confirmed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    need_id: Mapped[int] = mapped_column(ForeignKey("food_needs.id", ondelete="CASCADE"))
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    meals: Mapped[int] = mapped_column(Integer)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    match: Mapped[Match] = relationship(back_populates="stops")
    organization: Mapped[Organization] = relationship()


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        CheckConstraint(_in("status", DELIVERY_STATUSES), name="ck_deliveries_status"),
        Index("ix_deliveries_driver_status", "driver_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rescue_id: Mapped[int] = mapped_column(ForeignKey("food_rescues.id", ondelete="CASCADE"), unique=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), unique=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(24), default="HEADING_TO_RESTAURANT")
    meals: Mapped[int] = mapped_column(Integer)
    weight_lbs: Mapped[float] = mapped_column(Float, default=0)
    route: Mapped[dict] = mapped_column(JSON)
    status_history: Mapped[list] = mapped_column(JSON, default=list)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_demo_seed: Mapped[bool] = mapped_column(Boolean, default=False)

    rescue: Mapped[FoodRescue] = relationship()
    match: Mapped[Match] = relationship()
    driver: Mapped[Driver] = relationship()


class ImpactEvent(Base):
    """One row per confirmed drop off. Read by intelligence.compute_impact."""

    __tablename__ = "impact_events"
    __table_args__ = (CheckConstraint("meals > 0", name="ck_impact_meals"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.id", ondelete="CASCADE"), index=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"))
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    meals: Mapped[int] = mapped_column(Integer)
    weight_lbs: Mapped[float] = mapped_column(Float, default=0)
    delivery_minutes: Mapped[float] = mapped_column(Float, default=0)
    is_demo_seed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


DISPOSITIONS = ("discarded", "composted", "donated", "sold_discounted", "staff_meal", "no_surplus")


class SurplusLog(Base):
    """One day of the seven-day kitchen surplus log.

    Belongs to either a researched prospect (entered by an admin from what the
    business reports) or an enrolled restaurant (entered by its own staff).
    Quantities are self-reported, and labeled that way everywhere they appear.
    """

    __tablename__ = "surplus_logs"
    __table_args__ = (
        CheckConstraint("(prospect_id IS NULL) != (restaurant_id IS NULL)", name="ck_surplus_logs_owner"),
        CheckConstraint("surplus_meals >= 0", name="ck_surplus_logs_meals"),
        CheckConstraint("surplus_lbs >= 0", name="ck_surplus_logs_lbs"),
        CheckConstraint(_in("disposition", DISPOSITIONS), name="ck_surplus_logs_disposition"),
        UniqueConstraint("prospect_id", "log_date", name="uq_surplus_logs_prospect_day"),
        UniqueConstraint("restaurant_id", "log_date", name="uq_surplus_logs_restaurant_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prospect_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    restaurant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=True, index=True)
    log_date: Mapped[date] = mapped_column(Date)
    surplus_meals: Mapped[int] = mapped_column(Integer, default=0)
    surplus_lbs: Mapped[float] = mapped_column(Float, default=0)
    safe_to_donate: Mapped[bool] = mapped_column(Boolean, default=False)
    disposition: Mapped[str] = mapped_column(String(20), default="no_surplus")
    food_categories: Mapped[str] = mapped_column(String(200), default="")
    ready_time: Mapped[str] = mapped_column(String(20), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    reported_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TripLeg(Base):
    """A driving leg with its real duration, logged for retraining the ETA model."""

    __tablename__ = "trip_legs"
    __table_args__ = (CheckConstraint("actual_minutes >= 0", name="ck_trip_legs_minutes"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.id", ondelete="CASCADE"), index=True)
    leg_index: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime] = mapped_column(DateTime)
    actual_minutes: Mapped[float] = mapped_column(Float)
    predicted_p50: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    features: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
