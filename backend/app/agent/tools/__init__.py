from datetime import datetime, timedelta, timezone

from claude_agent_sdk import create_sdk_mcp_server, tool
from sqlalchemy import select

from app.agent.embeddings import embed_text
from app.db.session import async_session_factory
from app.models import Competitor, Development, PriceObservation, Product, SWOTAnalysis

SWOT_AGENT_MODEL = "claude-sonnet-5"


async def _find_competitor(session, slug: str) -> Competitor | None:
    result = await session.execute(select(Competitor).where(Competitor.slug == slug))
    return result.scalar_one_or_none()


def _error(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "is_error": True}


@tool(
    "query_price_history",
    "Look up recorded price history for a tracked company's products, "
    "optionally filtered by product name and time range. Works for real "
    "competitors AND for our own company (slug 'gurneys') — both are "
    "tracked the same way; pass competitor='gurneys' for our own pricing.",
    {"competitor": str, "product_query": str, "days": int},
)
async def query_price_history(args: dict) -> dict:
    async with async_session_factory() as session:
        competitor = await _find_competitor(session, args["competitor"])
        if competitor is None:
            return _error(f"No competitor with slug {args['competitor']!r}")

        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=args["days"])
        stmt = (
            select(Product, PriceObservation)
            .join(PriceObservation, PriceObservation.product_id == Product.id)
            .where(
                Product.competitor_id == competitor.id,
                Product.name.ilike(f"%{args['product_query']}%"),
                PriceObservation.observed_at >= since,
            )
            .order_by(Product.name, PriceObservation.observed_at)
        )
        rows = (await session.execute(stmt)).all()

    if not rows:
        return {"content": [{"type": "text", "text": "No matching price history found."}]}

    lines = [
        f"{product.name}: {obs.price} {obs.currency} "
        f"({'in stock' if obs.in_stock else 'out of stock'}) at {obs.observed_at.isoformat()}"
        for product, obs in rows
    ]
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "search_developments",
    "Semantically search a tracked company's recorded developments (news, "
    "launches, promos, funding, leadership changes) by meaning, not just "
    "keywords. Works for real competitors AND for our own company (slug "
    "'gurneys') — pass competitor='gurneys' for our own developments.",
    {"competitor": str, "query": str, "top_k": int},
)
async def search_developments(args: dict) -> dict:
    async with async_session_factory() as session:
        competitor = await _find_competitor(session, args["competitor"])
        if competitor is None:
            return _error(f"No competitor with slug {args['competitor']!r}")

        query_vector = await embed_text(args["query"], input_type="query")
        stmt = (
            select(Development)
            .where(Development.competitor_id == competitor.id)
            .order_by(Development.embedding.cosine_distance(query_vector))
            .limit(args["top_k"])
        )
        developments = (await session.execute(stmt)).scalars().all()

    if not developments:
        return {"content": [{"type": "text", "text": "No matching developments found."}]}

    lines = [
        f"[{d.category}] {d.title} ({d.event_date.date().isoformat()}): {d.summary}"
        for d in developments
    ]
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "save_swot_analysis",
    "Persist a completed SWOT analysis for a competitor.",
    {
        "type": "object",
        "properties": {
            "competitor": {"type": "string"},
            "strengths": {"type": "array", "items": {"type": "string"}},
            "weaknesses": {"type": "array", "items": {"type": "string"}},
            "opportunities": {"type": "array", "items": {"type": "string"}},
            "threats": {"type": "array", "items": {"type": "string"}},
            "source_summary": {"type": "string"},
        },
        "required": [
            "competitor",
            "strengths",
            "weaknesses",
            "opportunities",
            "threats",
            "source_summary",
        ],
    },
)
async def save_swot_analysis(args: dict) -> dict:
    async with async_session_factory() as session:
        competitor = await _find_competitor(session, args["competitor"])
        if competitor is None:
            return _error(f"No competitor with slug {args['competitor']!r}")

        session.add(
            SWOTAnalysis(
                competitor_id=competitor.id,
                strengths=args["strengths"],
                weaknesses=args["weaknesses"],
                opportunities=args["opportunities"],
                threats=args["threats"],
                model_used=SWOT_AGENT_MODEL,
                source_summary=args["source_summary"],
            )
        )
        await session.commit()

    return {"content": [{"type": "text", "text": "SWOT analysis saved."}]}


@tool(
    "save_development",
    "Persist a newly discovered competitor development (news, launch, "
    "promo, funding, leadership change, or other).",
    {"competitor": str, "title": str, "summary": str, "url": str, "category": str, "event_date": str},
)
async def save_development(args: dict) -> dict:
    async with async_session_factory() as session:
        competitor = await _find_competitor(session, args["competitor"])
        if competitor is None:
            return _error(f"No competitor with slug {args['competitor']!r}")

        embedding = await embed_text(f"{args['title']}\n{args['summary']}", input_type="document")
        session.add(
            Development(
                competitor_id=competitor.id,
                title=args["title"],
                summary=args["summary"],
                url=args["url"],
                category=args["category"],
                event_date=datetime.fromisoformat(args["event_date"]),
                embedding=embedding,
            )
        )
        await session.commit()

    return {"content": [{"type": "text", "text": "Development saved."}]}


competitor_analysis_server = create_sdk_mcp_server(
    name="competitor_analysis",
    tools=[query_price_history, search_developments, save_swot_analysis, save_development],
)
