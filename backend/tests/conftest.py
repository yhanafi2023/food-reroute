"""Test setup: an isolated SQLite file and offline routing, set before the app is imported."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_tmp = tempfile.mkdtemp(prefix="foodflow-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DEMO_MODE"] = "true"
os.environ["ROUTING_PROVIDER"] = "offline"
os.environ["JWT_SECRET"] = "test-secret-at-least-32-bytes-long-000"
os.environ.pop("MAPBOX_ACCESS_TOKEN", None)
