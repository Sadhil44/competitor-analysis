"""FastAPI app entry point.

Phase 0 scope: app boots, exposes a health check that also proves the
competitors.yaml config loads and validates. Data/agent/scheduler routers
get mounted here in later phases (see app/api/).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings, load_competitors_config

app = FastAPI(title="Competitor Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    competitors = load_competitors_config()
    return {
        "status": "ok",
        "environment": settings.environment,
        "active_competitors": [c.slug for c in competitors],
    }
