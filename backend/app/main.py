"""FastAPI app entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import activity, agent, campaigns, competitors, developments, intelligence, prices, products, swot
from app.core.config import get_settings, load_competitors_config

app = FastAPI(title="Competitor Analysis API")

app.add_middleware(
    CORSMiddleware,
    # "localhost" and "127.0.0.1" are different origins as far as CORS'
    # exact-string allowlist is concerned, even though they're the same
    # machine — and on Windows + Docker Desktop, "localhost" can silently
    # fail to resolve to the container's IPv4 port mapping (resolves to
    # ::1 first, which Docker Desktop doesn't forward), making 127.0.0.1
    # the address that actually works. Both need to be allowed, or the
    # browser-side ask-agent fetch fails outright depending on which one
    # the user's browser happens to use.
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://host.docker.internal:3000"],
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


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    competitors = load_competitors_config()
    return {
        "status": "ok",
        "environment": settings.environment,
        "active_competitors": [c.slug for c in competitors],
    }
