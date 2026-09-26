"""Settings from environment variables (backend/.env is loaded if present)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'foodflow.db'}")
if DATABASE_URL.startswith("postgres://"):  # Render style URL
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me-in-backend-dot-env")
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
os.environ.setdefault("DEMO_MODE", "true")
DEMO_MODE = _bool("DEMO_MODE", True)
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
TIMEZONE = os.getenv("TIMEZONE", "America/New_York")  # Miami-Dade
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
RUN_SCHEDULER = _bool("RUN_SCHEDULER", True)
SCHEDULER_SECONDS = int(os.getenv("SCHEDULER_SECONDS", "30"))

# Teammate services over HTTP. Empty: use the in-process modules (logistics / intelligence).
ROUTING_SERVICE_URL = os.getenv("ROUTING_SERVICE_URL", "").rstrip("/")
ALLOCATION_SERVICE_URL = os.getenv("ALLOCATION_SERVICE_URL", "").rstrip("/")
SERVICE_TIMEOUT_SECONDS = float(os.getenv("SERVICE_TIMEOUT_SECONDS", "3"))

# Notifications: console always; email if SMTP_HOST is set; SMS if Twilio keys are set.
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "FoodFlow <no-reply@foodflow.local>")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.getenv("TWILIO_FROM", "")
