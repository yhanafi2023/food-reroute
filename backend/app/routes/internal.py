"""Scheduled jobs over HTTP, for deployments without a long-running process (Vercel).

A scheduler (Vercel Cron, or Supabase pg_cron + pg_net) calls GET or POST /internal/jobs/run
every minute with "Authorization: Bearer <CRON_SECRET>". Off (404) unless CRON_SECRET is set.
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


@router.api_route("/internal/jobs/run", methods=["GET", "POST"], include_in_schema=False)
def run_scheduled_jobs(authorization: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    if not config.CRON_SECRET:
        raise HTTPException(404, "Not Found")
    if not hmac.compare_digest((authorization or "").encode(), f"Bearer {config.CRON_SECRET}".encode()):
        raise HTTPException(401, "Unauthorized")
    return run_jobs_exclusive(db)
