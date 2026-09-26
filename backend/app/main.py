"""This file: FoodFlow API. Run from backend/: uvicorn app.main:app --reload --port 8000"""
#libraries: Async- for asynchronus tasks(i.e., the scheduler.
#logging- prints useful information to terminal
#asnyccontextmanager- used to create something that runs
import asyncio
import logging
from contextlib import asynccontextmanager

#importing fastapi- web frame work.... 2nd for front seperate from back
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware # controls whether front end is allowed to have comms with back

from app.config import CORS_ORIGIN_REGEX, CORS_ORIGINS, DEMO_MODE, RUN_SCHEDULER, SCHEDULER_SECONDS, check_secrets
from app.idempotency import IdempotencyMiddleware
from app.routes import (
    analytics_routes, auth_routes, community_need, dashboards, internal, me, onboarding, prospects, records, rescues,
    trips,
)

logging.basicConfig(level=logging.INFO)
check_secrets()  # refuse to serve with a guessable JWT secret outside local demo mode


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Outside demo mode the schema is owned by migrations (alembic upgrade head), never created here.
    if DEMO_MODE:
        from app.seed import seed_if_empty

        seed_if_empty()
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
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_origin_regex=CORS_ORIGIN_REGEX,
                   allow_credentials=False, allow_methods=["*"],
                   allow_headers=["*"], expose_headers=["Idempotent-Replayed"])
for module in (auth_routes, me, onboarding, rescues, trips, records, analytics_routes, prospects, community_need,
              dashboards, internal):
    app.include_router(module.router)


@app.get("/")
def health():
    return {"name": "FoodFlow API", "status": "ok", "demo_mode": DEMO_MODE}
