"""One clock for the whole backend, so tests and simulations can control time.

All stored times are naive UTC. Local rules (receiving hours, closing times) use
TIMEZONE from config. Tests call `set_fake(FakeClock(...))`; simulations run
inside `use(FakeClock(...))`, which only affects the current thread of work.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional
from zoneinfo import ZoneInfo

from app.config import TIMEZONE

LOCAL_TZ = ZoneInfo(TIMEZONE)


class FakeClock:
    def __init__(self, start: datetime):
        self.current = start.replace(tzinfo=None) if start.tzinfo is None else start.astimezone(timezone.utc).replace(tzinfo=None)

    def now(self) -> datetime:
        return self.current

    def advance(self, minutes: float = 0, seconds: float = 0) -> datetime:
        self.current += timedelta(minutes=minutes, seconds=seconds)
        return self.current


_ctx: ContextVar[Optional[FakeClock]] = ContextVar("foodflow_clock", default=None)
_global: Optional[FakeClock] = None


def now() -> datetime:
    fake = _ctx.get() or _global
    return fake.now() if fake else datetime.now(timezone.utc).replace(tzinfo=None)


def set_fake(fake: Optional[FakeClock]) -> None:
    """Process-wide fake clock (tests)."""
    global _global
    _global = fake


@contextmanager
def use(fake: FakeClock) -> Iterator[FakeClock]:
    """Fake clock for the current context only (simulations)."""
    token = _ctx.set(fake)
    try:
        yield fake
    finally:
        _ctx.reset(token)


def to_local(dt_utc: datetime) -> datetime:
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)


def local_to_utc(dt_local: datetime) -> datetime:
    if dt_local.tzinfo is None:
        dt_local = dt_local.replace(tzinfo=LOCAL_TZ)
    return dt_local.astimezone(timezone.utc).replace(tzinfo=None)


def fmt_local(dt_utc: datetime) -> str:
    """'11:40 PM' style local time."""
    return to_local(dt_utc).strftime("%-I:%M %p")
