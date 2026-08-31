"""FastAPI app entry point."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Uvicorn only configures its own "uvicorn"/"uvicorn.access" loggers — every
# app module's plain `logging.getLogger(__name__).info(...)` (ingest.py's
# per-page/per-crawl progress, the scheduler's job lifecycle, etc.) was
# silently dropped by the root logger's default WARNING level, with no
# error to indicate why nothing showed up in `docker compose logs backend`.
# Set once, at import time, rather than in the lifespan below, so it's also
# in effect for one-off scripts that import app.main indirectly.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from app.api import (
    activity,
    agent,
    campaigns,
    competitors,
    developments,
    intelligence,
    prices,
    products,
    scheduler as scheduler_api,
    swot,
)
from app.core.config import get_settings, load_competitors_config
from app.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Skipped under pytest (which sets this env var for the duration of
    # every test): the test client's ASGITransport runs this same lifespan
    # on every test that uses it, and there's no reason for a test run to
    # spin up a real AsyncIOScheduler with real crawl jobs registered
    # against it, only to tear it down a moment later.
    running_under_pytest = "PYTEST_CURRENT_TEST" in os.environ
    if not running_under_pytest:
        start_scheduler()
    yield
    if not running_under_pytest:
        shutdown_scheduler()


app = FastAPI(title="Competitor Analysis API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # "localhost" and "127.0.0.1" are different origins as far as CORS'
    # exact-string allowlist is concerned, even though they're the same
    # machine — and on Windows + Docker Desktop, "localhost" can silently
    # fail to resolve to the container's IPv4 port mapping (resolves to
    # ::1 first, which Docker Desktop doesn't forward), making 127.0.0.1
    # the address that actually works. Both need to be allowed, or the
    # browser-side ask-agent fetch fails outright depending on which one
    # the user's browser happens to use. FRONTEND_ORIGINS adds the deployed
    # frontend's real origin (e.g. the Vercel URL) on top of these — there
    # is no "localhost" in production at all.
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://host.docker.internal:3000",
        *get_settings().frontend_origin_list,
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(competitors.router)
app.include_router(products.router)
app.include_router(prices.router)
app.include_router(agent.router)
app.include_router(swot.router)
app.include_router(developments.router)
app.include_router(campaigns.router)
app.include_router(intelligence.router)
app.include_router(activity.router)
app.include_router(scheduler_api.router)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    competitors = load_competitors_config()
    return {
        "status": "ok",
        "environment": settings.environment,
        "active_competitors": [c.slug for c in competitors],
    }
