"""Scheduled jobs over HTTP, for deployments without a long-running process (Vercel).

A scheduler calls GET or POST /internal/jobs/run every minute, authorized by either
- "Authorization: Bearer <CRON_SECRET>" (Vercel Cron sends this itself), or
- "apikey: <SUPABASE_SECRET_KEY>" (Supabase pg_cron + pg_net, with the key read from Vault).
Off (404) unless CRON_SECRET or SUPABASE_SECRET_KEY is set.
Overlapping or duplicate calls are safe: the jobs run under a lease (app/jobs.py).
"""
import hmac
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app import config
from app.db import get_db
from app.jobs import run_jobs_exclusive

router = APIRouter(tags=["internal"])


def _matches(sent: Optional[str], expected: str) -> bool:
    return bool(expected) and hmac.compare_digest((sent or "").encode(), expected.encode())


@router.api_route("/internal/jobs/run", methods=["GET", "POST"], include_in_schema=False)
def run_scheduled_jobs(authorization: Optional[str] = Header(default=None), apikey: Optional[str] = Header(default=None),
                       db: Session = Depends(get_db)):
    if not config.CRON_SECRET and not config.SUPABASE_SECRET_KEY:
        raise HTTPException(404, "Not Found")
    if not (_matches(authorization, f"Bearer {config.CRON_SECRET}" if config.CRON_SECRET else "")
            or _matches(apikey, config.SUPABASE_SECRET_KEY)):
        raise HTTPException(401, "Unauthorized")
    return run_jobs_exclusive(db)
