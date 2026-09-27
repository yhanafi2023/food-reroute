"""Settings from environment variables (backend/.env is loaded if present)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def database_url(raw: str) -> str:
    """Supabase, Render and Heroku hand out postgres:// or postgresql:// URLs; use the psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if raw.startswith(prefix):
            return "postgresql+psycopg://" + raw[len(prefix):]
    return raw


DATABASE_URL = database_url(os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'foodflow.db'}"))
os.environ.setdefault("DEMO_MODE", "true")
DEMO_MODE = _bool("DEMO_MODE", True)
# Vercel sets VERCEL=1: every request may land on a fresh, short-lived instance.
SERVERLESS = _bool("SERVERLESS", bool(os.getenv("VERCEL")))

DEV_JWT_SECRET = "dev-only-secret-change-me-in-backend-dot-env"
JWT_SECRET = os.getenv("JWT_SECRET", DEV_JWT_SECRET)


def check_secrets() -> None:
    """Called when the web app starts (app/main.py); scripts such as migrations don't need the secret."""
    if (not DEMO_MODE or SERVERLESS) and (len(JWT_SECRET) < 32 or JWT_SECRET in (
            DEV_JWT_SECRET, "replace-with-a-long-random-string")):
        raise RuntimeError("Set JWT_SECRET to a random string of at least 32 characters, e.g. "
                           "python -c \"import secrets; print(secrets.token_urlsafe(48))\"")


JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
# Optional regex for extra origins, e.g. Vercel previews: https://food-reroute-[a-z0-9-]+\.vercel\.app
CORS_ORIGIN_REGEX = os.getenv("CORS_ORIGIN_REGEX") or None
TIMEZONE = os.getenv("TIMEZONE", "America/New_York")  # Miami-Dade
# The in-process loop suits one long-running server; serverless deployments call /internal/jobs/run on a schedule.
RUN_SCHEDULER = _bool("RUN_SCHEDULER", not SERVERLESS)
SCHEDULER_SECONDS = int(os.getenv("SCHEDULER_SECONDS", "30"))
# Shared secret for the scheduled jobs endpoint (sent as "Authorization: Bearer <CRON_SECRET>"). Empty: endpoint off.
CRON_SECRET = os.getenv("CRON_SECRET", "").strip()  # a pasted value often carries a trailing newline

# Supabase Auth, accepted alongside FoodFlow's own sessions (app/supabase_auth.py). Empty SUPABASE_URL: off.
# The secret key (sb_secret_...) also authorizes /internal/jobs/run, sent by pg_net in the "apikey" header.
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL") or (
    f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else "")

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
