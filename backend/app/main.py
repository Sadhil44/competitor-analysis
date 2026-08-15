"""FastAPI app entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent, campaigns, competitors, developments, prices, products, swot
from app.core.config import get_settings, load_competitors_config

app = FastAPI(title="Competitor Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    competitors = load_competitors_config()
    return {
        "status": "ok",
        "environment": settings.environment,
        "active_competitors": [c.slug for c in competitors],
    }
