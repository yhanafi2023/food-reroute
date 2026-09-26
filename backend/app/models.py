"""Database tables. All times are naive UTC (see app/clock.py).

Rules that must hold no matter which client calls the API are CHECK constraints
here; the rest are enforced in the services. audit_events is append-only
(triggers installed by app/db.py).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app import clock
from app.db import Base

ROLES = ("restaurant_staff", "restaurant_manager", "volunteer", "org_staff", "org_manager", "admin")
RESTAURANT_ROLES = ("restaurant_staff", "restaurant_manager")
ORG_ROLES = ("org_staff", "org_manager")
ORG_KINDS = ("restaurant", "receiver")
UNITS = ("individual_meal", "bag", "box", "tray", "half_pan", "full_pan")
CATEGORIES = ("hot", "cold", "frozen", "shelf_stable")
RESCUE_STATUSES = ("posted", "matched", "en_route_pickup", "picked_up", "en_route_dropoff", "delivered", "received",
                   "cancelled", "expired", "rejected", "reassigned")
TRIP_STATUSES = ("matched", "en_route_pickup", "picked_up", "en_route_dropoff", "delivered", "received",
                 "cancelled", "expired", "rejected", "reassigned")
HANDOFF_STATES = ("vehicle_arriving", "at_pickup_curb", "loading", "loaded", "in_transit", "at_dropoff_curb",
                  "unloaded", "received")
MODES = ("volunteer", "waymo_sim", "robot_sim")
STOP_STATUSES = ("pending", "delivered", "received", "rejected", "rerouted", "cancelled")
CONDITIONS = ("accepted", "partially_accepted", "rejected")
REJECT_REASONS = ("temperature", "packaging", "quantity", "other")
DISPOSITIONS = ("discarded", "composted", "donated", "sold_discounted", "staff_meal", "no_surplus")


def utcnow() -> datetime:
    return clock.now()


def _in(col: str, values) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (CheckConstraint(_in("kind", ORG_KINDS), name="ck_org_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(160))
    legal_name: Mapped[str] = mapped_column(String(200), default="")
    address: Mapped[str] = mapped_column(String(255), default="")
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    is_fictional: Mapped[bool] = mapped_column(Boolean, default=False)
    public_slug: Mapped[Optional[str]] = mapped_column(String(80), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    restaurant_profile: Mapped[Optional["RestaurantProfile"]] = relationship(back_populates="organization", uselist=False)
    receiver_profile: Mapped[Optional["ReceiverProfile"]] = relationship(back_populates="organization", uselist=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(_in("role", ROLES), name="ck_users_role"),
        # restaurant and org roles belong to an organization; volunteers and admins do not
        CheckConstraint("(role IN ('volunteer', 'admin')) = (organization_id IS NULL)", name="ck_users_org_membership"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))  # salted PBKDF2 (app/auth.py), never the password
    name: Mapped[str] = mapped_column(String(160))
    first_name: Mapped[str] = mapped_column(String(80), default="")
    role: Mapped[str] = mapped_column(String(24))
    organization_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    phone: Mapped[str] = mapped_column(String(40), default="")
    is_demo_account: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notification_prefs: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    organization: Mapped[Optional[Organization]] = relationship()


class LoginAttempt(Base):
    """A failed sign-in, keyed by "email:<address>" or "ip:<address>". Read by the login throttle
    (app/auth.py); kept in the database because serverless instances share no memory. Pruned by the jobs."""

    __tablename__ = "login_attempts"
    __table_args__ = (Index("ix_login_attempts_key_at", "key", "at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(300))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class JobLock(Base):
    """Lease so only one run of the scheduled jobs happens at a time, across instances and duplicate cron calls."""

    __tablename__ = "job_locks"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    locked_until: Mapped[datetime] = mapped_column(DateTime)


class RestaurantProfile(Base):
    __tablename__ = "restaurant_profiles"
    __table_args__ = (
        CheckConstraint("totes_on_hand >= 0 AND totes_out >= 0", name="ck_totes"),
        CheckConstraint("hauling_cost_per_lb IS NULL OR hauling_cost_per_lb >= 0", name="ck_hauling"),
    )

    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    closing_times: Mapped[dict] = mapped_column(JSON, default=dict)      # {"mon": "22:00", ...}
    staffed_until: Mapped[dict] = mapped_column(JSON, default=dict)      # {"mon": "23:30", ...} local time
    surplus_usually: Mapped[str] = mapped_column(String(200), default="")
    totes_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    totes_out: Mapped[int] = mapped_column(Integer, default=0)
    default_fmv_per_meal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    default_cost_basis_per_meal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    basis_election_25pct: Mapped[bool] = mapped_column(Boolean, default=False)
    pickup_instructions: Mapped[str] = mapped_column(Text, default="")
    hauling_cost_per_lb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # only if the restaurant enters it
    public_partner_page: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    organization: Mapped[Organization] = relationship(back_populates="restaurant_profile")


class ReceiverProfile(Base):
    """Answers to the three onboarding questions, as columns for matching and reporting.
    Each answer set is also kept in intake_answers with who answered and when."""

    __tablename__ = "receiver_profiles"
    __table_args__ = (
        CheckConstraint("cutoff_minutes IS NULL OR cutoff_minutes >= 0", name="ck_cutoff"),
        CheckConstraint("max_meals_per_delivery IS NULL OR max_meals_per_delivery > 0", name="ck_max_meals"),
        CheckConstraint("(NOT is_501c3 OR is_501c3 IS NULL) OR (ein IS NOT NULL AND ein != '')", name="ck_ein_required"),
    )

    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    # Q1
    schedule: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {"mon": [["09:00","17:00"]], "sun": []}
    cutoff_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    receiving_contact_name: Mapped[str] = mapped_column(String(120), default="")
    receiving_contact_phone: Mapped[str] = mapped_column(String(40), default="")
    receiving_instructions: Mapped[str] = mapped_column(Text, default="")
    curbside_ok: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    curb_location: Mapped[str] = mapped_column(String(200), default="")
    # Q2
    accepts_hot: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    hot_max_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    can_hold_hot: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    serves_immediately: Mapped[str] = mapped_column(String(200), default="")
    accepts_cold: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    fridge_capacity_meals: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    accepts_frozen: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    freezer_capacity_meals: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    accepts_shelf_stable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    dietary_rules: Mapped[list] = mapped_column(JSON, default=list)
    refused_allergens: Mapped[list] = mapped_column(JSON, default=list)
    max_meals_per_delivery: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    typical_nightly_need: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_need: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_need_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Q3
    required_fields: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    report_frequency: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    report_format: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    reports_to: Mapped[str] = mapped_column(String(300), default="")
    is_501c3: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    ein: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ein_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    ein_verified_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ein_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="receiver_profile")


class IntakeAnswer(Base):
    """History of onboarding answers (append a row per save). Latest per question wins."""

    __tablename__ = "intake_answers"
    __table_args__ = (
        CheckConstraint("question IN ('Q1', 'Q2', 'Q3')", name="ck_intake_question"),
        Index("ix_intake_org_q", "organization_id", "question", "answered_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    question: Mapped[str] = mapped_column(String(2))
    answers: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(40), default="self_reported_by_org")
    answered_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    answered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReceivingException(Base):
    __tablename__ = "receiving_exceptions"
    __table_args__ = (UniqueConstraint("organization_id", "day", name="uq_exception_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(200), default="")


class VolunteerProfile(Base):
    __tablename__ = "volunteer_profiles"
    __table_args__ = (
        CheckConstraint("capacity_meals > 0", name="ck_vol_capacity"),
        CheckConstraint("max_distance_mi > 0", name="ck_vol_distance"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    availability: Mapped[dict] = mapped_column(JSON, default=dict)  # {"mon": [["17:00","21:00"]]}
    max_distance_mi: Mapped[float] = mapped_column(Float, default=5)
    capacity_meals: Mapped[int] = mapped_column(Integer, default=40)
    has_cooler: Mapped[bool] = mapped_column(Boolean, default=False)
    has_insulated_bags: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_areas: Mapped[str] = mapped_column(String(200), default="")
    vehicle_description: Mapped[str] = mapped_column(String(120), default="")
    home_lat: Mapped[float] = mapped_column(Float)   # private: never returned to restaurants or orgs
    home_lng: Mapped[float] = mapped_column(Float)
    last_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_location_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship()


class RescueTemplate(Base):
    __tablename__ = "rescue_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    fields: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RecurringSchedule(Base):
    """'Every Friday 10 PM': creates a draft post that staff confirm with one action."""

    __tablename__ = "recurring_schedules"
    __table_args__ = (CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_sched_weekday"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("rescue_templates.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(Integer)  # 0 = Monday
    local_time: Mapped[str] = mapped_column(String(5))  # "22:00"
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_draft_for: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


class Rescue(Base):
    __tablename__ = "rescues"
    __table_args__ = (
        CheckConstraint(_in("status", RESCUE_STATUSES), name="ck_rescue_status"),
        CheckConstraint(_in("unit", UNITS), name="ck_rescue_unit"),
        CheckConstraint(_in("category", CATEGORIES), name="ck_rescue_category"),
        CheckConstraint("quantity > 0 AND est_meals > 0", name="ck_rescue_quantity"),
        CheckConstraint("is_draft OR (attested_by IS NOT NULL AND attested_at IS NOT NULL)", name="ck_rescue_attested"),
        Index("ix_rescue_status_safe_until", "status", "safe_until"),
        Index("ix_rescue_org_created", "restaurant_org_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    posted_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="posted")
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20))
    meals_per_unit: Mapped[float] = mapped_column(Float)       # snapshot of the assumption used
    est_meals: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(14))
    description: Mapped[str] = mapped_column(Text, default="")
    prepared_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    allergens: Mapped[list] = mapped_column(JSON, default=list)
    allergens_declared: Mapped[bool] = mapped_column(Boolean, default=False)
    dietary_tags: Mapped[list] = mapped_column(JSON, default=list)
    attested_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    attested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    safe_until: Mapped[datetime] = mapped_column(DateTime)
    pickup_deadline: Mapped[datetime] = mapped_column(DateTime)
    pickup_instructions: Mapped[str] = mapped_column(Text, default="")
    pickup_code: Mapped[str] = mapped_column(String(8))
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("recurring_schedules.id", ondelete="SET NULL"), nullable=True)
    duplicate_of: Mapped[Optional[int]] = mapped_column(ForeignKey("rescues.id", ondelete="SET NULL"), nullable=True)
    cancel_reason: Mapped[str] = mapped_column(String(300), default="")
    fmv_per_meal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_basis_per_meal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    allowed_modes: Mapped[list] = mapped_column(JSON, default=lambda: list(MODES))
    excluded_volunteer_ids: Mapped[list] = mapped_column(JSON, default=list)
    requeue_count: Mapped[int] = mapped_column(Integer, default=0)
    is_fictional: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    restaurant: Mapped[Organization] = relationship()
    trips: Mapped[List["Trip"]] = relationship(back_populates="rescue", order_by="Trip.id")


class Trip(Base):
    """One carrier run: a volunteer (possibly several stops) or one simulated vehicle (one stop)."""

    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint(_in("status", TRIP_STATUSES), name="ck_trip_status"),
        CheckConstraint(_in("mode", MODES), name="ck_trip_mode"),
        CheckConstraint(f"handoff_state IS NULL OR {_in('handoff_state', HANDOFF_STATES)}", name="ck_trip_handoff"),
        CheckConstraint("(mode = 'volunteer') = (volunteer_user_id IS NOT NULL)", name="ck_trip_carrier"),
        CheckConstraint("(mode = 'volunteer') OR simulated", name="ck_trip_av_simulated"),
        Index("ix_trip_volunteer_status", "volunteer_user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rescue_id: Mapped[int] = mapped_column(ForeignKey("rescues.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(12))
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    volunteer_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    vehicle_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="matched")
    handoff_state: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    mode_reason: Mapped[str] = mapped_column(Text, default="")
    estimated: Mapped[bool] = mapped_column(Boolean, default=False)  # routing or allocation fallback was used
    eta_pickup_at: Mapped[datetime] = mapped_column(DateTime)
    load_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    unload_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    picked_up_meals: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pickup_photo_url: Mapped[str] = mapped_column(String(500), default="")
    totes_used: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    route: Mapped[dict] = mapped_column(JSON, default=dict)
    is_fictional: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    rescue: Mapped[Rescue] = relationship(back_populates="trips")
    volunteer: Mapped[Optional[User]] = relationship()
    stops: Mapped[List["TripStop"]] = relationship(back_populates="trip", order_by="TripStop.seq")


class TripStop(Base):
    __tablename__ = "trip_stops"
    __table_args__ = (
        CheckConstraint(_in("status", STOP_STATUSES), name="ck_stop_status"),
        CheckConstraint("allocated_meals > 0", name="ck_stop_meals"),
        CheckConstraint(f"condition IS NULL OR {_in('condition', CONDITIONS)}", name="ck_stop_condition"),
        CheckConstraint(f"reject_reason IS NULL OR {_in('reject_reason', REJECT_REASONS)}", name="ck_stop_reject"),
        CheckConstraint("condition IS NULL OR condition = 'accepted' OR reject_reason IS NOT NULL", name="ck_stop_reason_required"),
        CheckConstraint("received_meals IS NULL OR received_meals >= 0", name="ck_stop_received"),
        Index("ix_stop_org_status", "organization_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    allocated_meals: Mapped[int] = mapped_column(Integer)
    dropoff_code: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(12), default="pending")
    eta_at: Mapped[datetime] = mapped_column(DateTime)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    received_meals: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    condition: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    reject_note: Mapped[str] = mapped_column(String(300), default="")
    temperature_f: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    received_by_name: Mapped[str] = mapped_column(String(120), default="")
    photo_url: Mapped[str] = mapped_column(String(500), default="")
    incomplete_fields: Mapped[list] = mapped_column(JSON, default=list)
    meals_served: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    approaching_notified: Mapped[bool] = mapped_column(Boolean, default=False)

    trip: Mapped[Trip] = relationship(back_populates="stops")
    organization: Mapped[Organization] = relationship()


class MatchingExplanation(Base):
    __tablename__ = "matching_explanations"

    id: Mapped[int] = mapped_column(primary_key=True)
    rescue_id: Mapped[int] = mapped_column(ForeignKey("rescues.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    eligible: Mapped[bool] = mapped_column(Boolean)
    reasons: Mapped[list] = mapped_column(JSON, default=list)       # [{"code": "closed", "text": "closed until 8:00 AM"}]
    estimated_arrival_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Weighted ranking breakdown (distance/urgency/demand/capacity/community_need + total),
    # set only for eligible organizations. See app.intelligence.allocation.score_need.
    score: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditEvent(Base):
    """Append-only chain of custody. Updates and deletes are blocked by database triggers."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_rescue_at", "rescue_id", "at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rescue_id: Mapped[Optional[int]] = mapped_column(ForeignKey("rescues.id", ondelete="SET NULL"), nullable=True)
    trip_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trips.id", ondelete="SET NULL"), nullable=True)
    stop_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trip_stops.id", ondelete="SET NULL"), nullable=True)
    entity: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(40))
    from_state: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    to_state: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(24), default="system")
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("key", "caller", name="uq_idem_key_caller"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120))
    caller: Mapped[str] = mapped_column(String(80))
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(300))
    status_code: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Notification(Base):
    """Outbox. The console provider marks messages sent; email/SMS providers deliver them."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    event: Mapped[str] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(10))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(10), default="queued")
    error: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Acknowledgment(Base):
    """Donor acknowledgment for one received drop off, for the receiving org to e-sign."""

    __tablename__ = "acknowledgments"
    __table_args__ = (CheckConstraint("status IN ('pending_signature', 'signed')", name="ck_ack_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stop_id: Mapped[int] = mapped_column(ForeignKey("trip_stops.id", ondelete="CASCADE"), unique=True)
    donor_org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    receiver_org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    content: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending_signature")
    signer_name: Mapped[str] = mapped_column(String(120), default="")
    signed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    signed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RecoveryAgreement(Base):
    """Written agreement between a restaurant and a recovery org (SB 1383 records)."""

    __tablename__ = "recovery_agreements"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    receiver_org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    signed_date: Mapped[date] = mapped_column(Date)
    document_url: Mapped[str] = mapped_column(String(500))
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OrgReport(Base):
    __tablename__ = "org_reports"
    __table_args__ = (UniqueConstraint("organization_id", "period_start", "period_end", "format", name="uq_org_report_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    format: Mapped[str] = mapped_column(String(5))
    fields: Mapped[list] = mapped_column(JSON)
    content: Mapped[str] = mapped_column(Text)  # CSV text, or base64 for PDF
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ImpactEvent(Base):
    """One row per received drop off. Read by intelligence.compute_impact."""

    __tablename__ = "impact_events"
    __table_args__ = (CheckConstraint("meals > 0", name="ck_impact_meals"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[int] = mapped_column(Integer, index=True)  # the trip id
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    meals: Mapped[int] = mapped_column(Integer)
    weight_lbs: Mapped[float] = mapped_column(Float, default=0)
    delivery_minutes: Mapped[float] = mapped_column(Float, default=0)
    is_demo_seed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SurplusLog(Base):
    """One day of the seven-day kitchen surplus log (self-reported).

    Belongs to either a researched prospect (entered by an admin from what the
    business reports) or an enrolled restaurant organization (entered by its staff).
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
    restaurant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
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
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    leg_index: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime] = mapped_column(DateTime)
    actual_minutes: Mapped[float] = mapped_column(Float)
    predicted_p50: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    features: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
