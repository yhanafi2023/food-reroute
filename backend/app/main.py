"""FoodFlow API. Run from backend/: uvicorn app.main:app --reload --port 8000"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import intelligence
from app.config import CORS_ORIGINS, DEMO_MODE
from app.db import Base, engine
from app.intelligence.eta.model import ensure_eta_model
from app.logistics.routing import provider
from app.routes import admin, auth_routes, dashboards, deliveries, prospects, rescues, tracking_routes
from app.seed import seed_if_empty


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if DEMO_MODE:
        seed_if_empty()
    else:
        Base.metadata.create_all(engine)
    intelligence.ensure_model()
    ensure_eta_model()
    yield


app = FastAPI(title="FoodFlow API", description="Good Food. Greater Impact.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])

for module in (auth_routes, rescues, deliveries, dashboards, admin, prospects, tracking_routes):
    app.include_router(module.router)


@app.get("/")
def health():
    return {"name": "FoodFlow API", "status": "ok", "demo_mode": DEMO_MODE, "routing": provider()}
