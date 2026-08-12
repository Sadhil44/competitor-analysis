"""LangChain-style tools shared by the orchestrator's subagents (see
app/agent/subagents/__init__.py).

Rewritten from the earlier Claude Agent SDK version: same underlying DB and
embedding logic, but as plain @tool-decorated async functions bound directly
per-agent instead of registered on a shared MCP server whose access was
gated only by prompt instructions (see app/agent/orchestrator.py's module
docstring for why LangGraph replaced the Agent SDK here).
"""

from datetime import datetime, timedelta, timezone

from anthropic import AsyncAnthropic
from langchain_core.tools import tool
from sqlalchemy import select

from app.agent.embeddings import embed_text
from app.db.session import async_session_factory
from app.models import Competitor, Development, PriceObservation, Product, SWOTAnalysis

SAVE_MODEL = "claude-sonnet-5"
# Haiku tier for web_search: this tool makes its own nested LLM call purely to
# drive Anthropic's server-side web_search tool and summarize results — cost
# should scale like the extraction pipeline's Haiku calls, not like the
# calling subagent's own reasoning (mirrors app/scraping/extractor.py).
SEARCH_MODEL = "claude-haiku-4-5"

_anthropic_client = AsyncAnthropic()


async def _find_competitor(session, slug: str) -> Competitor | None:
    result = await session.execute(select(Competitor).where(Competitor.slug == slug))
    return result.scalar_one_or_none()


@tool
async def query_price_history(competitor: str, product_query: str, days: int) -> str:
    """Look up recorded price history for a tracked company's products,
    optionally filtered by product name and time range. Works for real
    competitors AND for our own company (slug 'gurneys') — both are tracked
    the same way; pass competitor='gurneys' for our own pricing.
    """
    async with async_session_factory() as session:
        competitor_row = await _find_competitor(session, competitor)
        if competitor_row is None:
            return f"No competitor with slug {competitor!r}"

        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        stmt = (
            select(Product, PriceObservation)
            .join(PriceObservation, PriceObservation.product_id == Product.id)
            .where(
                Product.competitor_id == competitor_row.id,
                Product.name.ilike(f"%{product_query}%"),
                PriceObservation.observed_at >= since,
            )
            .order_by(Product.name, PriceObservation.observed_at)
        )
        rows = (await session.execute(stmt)).all()

    if not rows:
        return "No matching price history found."

    lines = [
        f"{product.name}: {f'{obs.price} {obs.currency}' if obs.price is not None else 'no price shown'} "
        f"({'in stock' if obs.in_stock else 'out of stock'}) at {obs.observed_at.isoformat()}"
        for product, obs in rows
    ]
    return "\n".join(lines)


@tool
async def search_developments(competitor: str, query: str, top_k: int) -> str:
    """Semantically search a tracked company's recorded developments (news,
    launches, promos, funding, leadership changes) by meaning, not just
    keywords. Works for real competitors AND for our own company (slug
    'gurneys') — pass competitor='gurneys' for our own developments.
    """
    async with async_session_factory() as session:
        competitor_row = await _find_competitor(session, competitor)
        if competitor_row is None:
            return f"No competitor with slug {competitor!r}"

        query_vector = await embed_text(query, input_type="query")
        stmt = (
            select(Development)
            .where(Development.competitor_id == competitor_row.id)
            .order_by(Development.embedding.cosine_distance(query_vector))
            .limit(top_k)
        )
        developments = (await session.execute(stmt)).scalars().all()

    if not developments:
        return "No matching developments found."

    return "\n".join(
        f"[{d.category}] {d.title} ({d.event_date.date().isoformat()}): {d.summary}"
        for d in developments
    )


@tool
async def save_swot_analysis(
    competitor: str,
    strengths: list[str],
    weaknesses: list[str],
    opportunities: list[str],
    threats: list[str],
    source_summary: str,
) -> str:
    """Persist a completed SWOT analysis for a competitor."""
    async with async_session_factory() as session:
        competitor_row = await _find_competitor(session, competitor)
        if competitor_row is None:
            return f"No competitor with slug {competitor!r}"

        session.add(
            SWOTAnalysis(
                competitor_id=competitor_row.id,
                strengths=strengths,
                weaknesses=weaknesses,
                opportunities=opportunities,
                threats=threats,
                model_used=SAVE_MODEL,
                source_summary=source_summary,
            )
        )
        await session.commit()

    return "SWOT analysis saved."


@tool
async def save_development(
    competitor: str, title: str, summary: str, url: str, category: str, event_date: str
) -> str:
    """Persist a newly discovered competitor development (news, launch,
    promo, funding, leadership change, or other). event_date is ISO format
    (e.g. 2026-07-01).
    """
    async with async_session_factory() as session:
        competitor_row = await _find_competitor(session, competitor)
        if competitor_row is None:
            return f"No competitor with slug {competitor!r}"

        embedding = await embed_text(f"{title}\n{summary}", input_type="document")
        session.add(
            Development(
                competitor_id=competitor_row.id,
                title=title,
                summary=summary,
                url=url,
                category=category,
                event_date=datetime.fromisoformat(event_date),
                embedding=embedding,
            )
        )
        await session.commit()

    return "Development saved."


@tool
async def web_search(query: str) -> str:
    """Search the web for current public information not found in recorded
    price history or developments — recent news, launches, or general
    company info. Use when the recorded data is thin or stale.
    """
    response = await _anthropic_client.messages.create(
        model=SEARCH_MODEL,
        max_tokens=1024,
        # allowed_callers must be explicit — Haiku 4.5 doesn't support the
        # programmatic-tool-calling caller the API otherwise defaults to.
        tools=[
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": 3,
                "allowed_callers": ["direct"],
            }
        ],
        messages=[{"role": "user", "content": query}],
    )

    lines: list[str] = []
    for block in response.content:
        if block.type == "text":
            lines.append(block.text)
        elif block.type == "web_search_tool_result" and isinstance(block.content, list):
            for result in block.content:
                url = getattr(result, "url", None)
                title = getattr(result, "title", None)
                if url:
                    lines.append(f"- {title or url}: {url}")

    return "\n".join(lines) if lines else "No results found."
