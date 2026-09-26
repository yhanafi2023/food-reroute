"""Deterministic demo controls (DEMO_MODE only).

The demo runs on its own clock, anchored at DEMO_CLOCK_START (local time, default Friday
2026-09-25 7:00 PM in Miami) so every run of the walkthrough sees the same open hours,
volunteer availability and deadlines. The clock advances with real time times `rate`,
and can be paused, advanced and reset. Everything here is fictional demo data.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

from app import clock

DEFAULT_START_LOCAL = "2026-09-25T19:00"

# persona -> demo account email (all fictional, see app/seed.py)
PERSONAS: Dict[str, Dict[str, str]] = {
    "restaurant": {"email": "staff@casa-demo.example.com", "label": "Restaurant staff, Casa Demo Cocina"},
    "volunteer": {"email": "marcus@volunteer-demo.example.com", "label": "Volunteer driver, Marcus"},
    "org": {"email": "staff@shelter-demo.example.com", "label": "Receiving staff, Demo Night Shelter"},
    "coordinator": {"email": "admin@foodflow-demo.example.com", "label": "Coordinator (admin)"},
}


class DemoClock(clock.FakeClock):
    """A fake clock that moves with real time (times `rate`) unless paused."""

    def __init__(self, start_utc: datetime, rate: float = 1.0):
        super().__init__(start_utc)
        self.start_utc = self.current
        self.rate = rate
        self.running = True
        self._real = time.monotonic()
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            if not self.running:
                return self.current
            return self.current + timedelta(seconds=(time.monotonic() - self._real) * self.rate)

    def _rebase(self) -> None:
        self.current = self.now()
        self._real = time.monotonic()

    def advance(self, minutes: float = 0, seconds: float = 0) -> datetime:
        self._rebase()
        with self._lock:
            self.current += timedelta(minutes=minutes, seconds=seconds)
        return self.current

    def pause(self) -> None:
        self._rebase()
        self.running = False

    def play(self, rate: Optional[float] = None) -> None:
        self._rebase()
        if rate is not None:
            self.rate = rate
        self.running = True

    def restart(self) -> None:
        with self._lock:
            self.current, self._real, self.running = self.start_utc, time.monotonic(), True


_demo: Optional[DemoClock] = None


def start_utc() -> datetime:
    raw = os.getenv("DEMO_CLOCK_START", DEFAULT_START_LOCAL)
    return clock.local_to_utc(datetime.fromisoformat(raw))


def install() -> Optional[DemoClock]:
    """Use the demo clock for the whole process unless DEMO_CLOCK_START=real."""
    global _demo
    if os.getenv("DEMO_CLOCK_START", "").strip().lower() == "real":
        return None
    _demo = DemoClock(start_utc(), float(os.getenv("DEMO_CLOCK_RATE", "1")))
    clock.set_fake(_demo)
    return _demo


def current() -> Optional[DemoClock]:
    return _demo


def state() -> dict:
    now = clock.now()
    d = _demo
    return {"demo_clock": d is not None, "running": d.running if d else True, "rate": d.rate if d else 1.0,
            "now": now.replace(microsecond=0).isoformat() + "Z", "local_time": clock.to_local(now).strftime("%a %b %-d, %-I:%M %p"),
            "start_local": clock.to_local(d.start_utc).strftime("%a %b %-d, %-I:%M %p") if d else None,
            "personas": {k: v["label"] for k, v in PERSONAS.items()},
            "label": "Fictional demo data on a demo clock" if d else "Fictional demo data"}


def reset() -> dict:
    """Restart the clock at its start and rebuild the fictional seed (history runs the real services)."""
    from app.seed import reset_database

    if _demo is not None:
        _demo.restart()
        _demo.pause()
    t0 = time.monotonic()
    reset_database()
    if _demo is not None:
        _demo.restart()
    return {**state(), "reset_seconds": round(time.monotonic() - t0, 2)}
