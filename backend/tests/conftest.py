"""Test setup: isolated SQLite file, offline routing, no background scheduler, fake clock helpers."""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_tmp = tempfile.mkdtemp(prefix="foodflow-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DEMO_MODE"] = "true"
os.environ["ROUTING_PROVIDER"] = "offline"
os.environ["RUN_SCHEDULER"] = "false"
os.environ["JWT_SECRET"] = "test-secret-at-least-32-bytes-long-000"
os.environ.pop("MAPBOX_ACCESS_TOKEN", None)
os.environ.pop("SMTP_HOST", None)
os.environ.pop("TWILIO_ACCOUNT_SID", None)

from app import auth, clock  # noqa: E402

# Hashing cost is not what these tests check, and each stored hash records its own iteration count.
auth.PASSWORD_ITERATIONS = 1_000

# Friday 2026-09-25, 7:00 PM in Miami (EDT, UTC-4) = 23:00 UTC
FRIDAY_7PM = datetime(2026, 9, 25, 23, 0)


@pytest.fixture()
def fake_clock():
    fc = clock.FakeClock(FRIDAY_7PM)
    clock.set_fake(fc)
    yield fc
    clock.set_fake(None)
