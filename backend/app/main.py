"""FoodFlow API. Run from backend/: uvicorn app.main:app --reload --port 8000"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS, DEMO_MODE, RUN_SCHEDULER, SCHEDULER_SECONDS
from app.db import create_schema
from app.idempotency import IdempotencyMiddleware
from app.routes import analytics_routes, auth_routes, me, onboarding, prospects, records, rescues, tax_routes, trips

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if DEMO_MODE:
        from app.seed import seed_if_empty

        seed_if_empty()
    else:
        create_schema()
    task = None
    if RUN_SCHEDULER:
        task = asyncio.create_task(_scheduler())
    yield
    if task:
        task.cancel()


async def _scheduler():
    """Runs the scheduled checks (no-shows, expiry, AV windows, reminders, reports)."""
    from app.jobs import run_jobs_now

    while True:
        await asyncio.sleep(SCHEDULER_SECONDS)
        try:
            await asyncio.to_thread(run_jobs_now)
        except Exception:  # never let one failed run stop the scheduler
            logging.getLogger("foodflow.jobs").exception("scheduled jobs failed")


app = FastAPI(title="FoodFlow API", description="Food rescue logistics: restaurants, volunteers, simulated AVs, receiving orgs.",
              lifespan=lifespan)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=False, allow_methods=["*"],
                   allow_headers=["*"], expose_headers=["Idempotent-Replayed"])
for module in (auth_routes, me, onboarding, rescues, trips, records, tax_routes, analytics_routes, prospects):
    app.include_router(module.router)


@app.get("/")
def health():
    return {"name": "FoodFlow API", "status": "ok", "demo_mode": DEMO_MODE}
