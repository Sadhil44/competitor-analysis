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
from sqlalchemy import func, or_, select

from app.agent.embeddings import embed_text
from app.db.session import async_session_factory
from app.intelligence import RAISED_BED_TYPES, WORKBENCH_SLUGS
from app.intelligence.matching import find_comparables
from app.intelligence.text import name_matches_query, significant_keywords
from app.models import Campaign, Competitor, Development, PriceObservation, Product, SWOTAnalysis

SAVE_MODEL = "claude-sonnet-5"
# Haiku tier for web_search: this tool makes its own nested LLM call purely to
# drive Anthropic's server-side web_search tool and summarize results — cost
# should scale like the extraction pipeline's Haiku calls, not like the
# calling subagent's own reasoning (mirrors app/scraping/extractor.py).
SEARCH_MODEL = "claude-haiku-4-5"

_anthropic_client = AsyncAnthropic()


async def _find_competitor(session, slug: str) -> Competitor | None:
    """Resolves the model's best-guess competitor identifier to a row.

    The agent is never given the exact stored slug list, so it often passes
    a close approximation — different casing/spacing, or a singular/plural
    mismatch like "Holland Bulb Farm" vs. the stored "Holland Bulb Farms".
    Falls back from an exact slug match to a normalized-slug and then a
    loose substring match against slug or name, rather than reporting the
    competitor untracked over a naming near-miss.
    """
    result = await session.execute(select(Competitor).where(Competitor.slug == slug))
    row = result.scalar_one_or_none()
    if row is not None:
        return row

    normalized = slug.strip().lower().replace(" ", "-").replace("_", "-")
    result = await session.execute(
        select(Competitor)
        .where(or_(Competitor.slug.ilike(f"%{normalized}%"), Competitor.name.ilike(f"%{slug}%")))
        .order_by(func.length(Competitor.slug))
    )
    return result.scalars().first()


@tool
async def query_price_history(competitor: str, product_query: str, days: int) -> str:
    """Look up recorded price history for a tracked company's products,
    optionally filtered by product name and time range. Works for real
    competitors AND for our own company (slug 'gurneys') — both are tracked
    the same way; pass competitor='gurneys' for our own pricing. Each line
    is prefixed with [product_id=N] — pass that id to save_campaign if you
    later save a promotion tied to one of these specific products.
    """
    async with async_session_factory() as session:
        competitor_row = await _find_competitor(session, competitor)
        if competitor_row is None:
            return f"No competitor with slug {competitor!r}"

        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

        # Bidirectional keyword-overlap match, not a literal substring — a
        # query like "workbench" must still find a product actually named
        # "Cedar Potting Bench"/"Cedar Bench Kit". Neither ilike(f"%{query}%")
        # NOR an OR'd-keyword ilike catches that: "workbench" isn't a
        # substring of "Cedar Potting Bench" either way — the name's own
        # word "bench" is a substring of the query word "workbench", which
        # only name_matches_query's word-by-word check finds (see
        # app/intelligence/text.py's docstring for the full story). Fetching
        # candidates by competitor first (cheap, indexed) and filtering in
        # Python is what makes that check possible at all — it isn't
        # expressible as a single ilike clause.
        keywords = significant_keywords(product_query)
        candidates = (
            await session.execute(select(Product).where(Product.competitor_id == competitor_row.id))
        ).scalars().all()
        matched_ids = [p.id for p in candidates if name_matches_query(p.name, keywords)]
        if not matched_ids:
            return "No matching price history found."

        stmt = (
            select(Product, PriceObservation)
            .join(PriceObservation, PriceObservation.product_id == Product.id)
            .where(Product.id.in_(matched_ids), PriceObservation.observed_at >= since)
            .order_by(Product.name, PriceObservation.observed_at)
            # Full-catalog crawls now put thousands of products behind one
            # competitor — capped so a broad query can't return an
            # unbounded result set.
            .limit(200)
        )
        rows = (await session.execute(stmt)).all()

    if not rows:
        return "No matching price history found."

    lines = [
        f"[product_id={product.id}] {product.name}: "
        f"{f'{obs.price} {obs.currency}' if obs.price is not None else 'no price shown'} "
        f"({'in stock' if obs.in_stock else 'out of stock'}) at {obs.observed_at.isoformat()}"
        for product, obs in rows
    ]
    return "\n".join(lines)


@tool
async def search_developments(competitor: str, query: str, top_k: int) -> str:
    """Semantically search a tracked company's recorded strategic/
    organizational developments (launches, funding, leadership changes,
    major assortment shifts) by meaning, not just keywords. Does NOT
    include promotions/sales — use search_campaigns for those. Works for
    real competitors AND for our own company (slug 'gurneys') — pass
    competitor='gurneys' for our own developments.
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
    """Persist a newly discovered STRATEGIC/organizational competitor
    development — category is one of: launch, funding, leadership,
    assortment_change, pr, other. Do NOT use this for sales/discounts/
    promotions — call save_campaign for those instead. event_date is ISO
    format (e.g. 2026-07-01).
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
async def search_campaigns(competitor: str, product_query: str = "") -> str:
    """List recorded promotional campaigns (sales, discounts, marketing
    pushes) for a tracked company, optionally filtered by product name.
    Works for real competitors AND for our own company (slug 'gurneys').
    Check this before calling save_campaign so you don't record a
    duplicate.
    """
    async with async_session_factory() as session:
        competitor_row = await _find_competitor(session, competitor)
        if competitor_row is None:
            return f"No competitor with slug {competitor!r}"

        stmt = select(Campaign).where(Campaign.competitor_id == competitor_row.id)
        if product_query:
            # Same bidirectional keyword-overlap match as query_price_history
            # (see its comment / app/intelligence/text.py) — fetch this
            # competitor's products first so a query like "workbench" can
            # still match a product named "Cedar Potting Bench".
            keywords = significant_keywords(product_query)
            candidates = (
                await session.execute(select(Product).where(Product.competitor_id == competitor_row.id))
            ).scalars().all()
            matched_ids = [p.id for p in candidates if name_matches_query(p.name, keywords)]
            if not matched_ids:
                return "No matching campaigns found."
            stmt = stmt.where(Campaign.product_id.in_(matched_ids))
        stmt = stmt.order_by(Campaign.discovered_at.desc()).limit(20)
        campaign_rows = (await session.execute(stmt)).scalars().all()

    if not campaign_rows:
        return "No matching campaigns found."

    lines = []
    for c in campaign_rows:
        window = ""
        if c.starts_at or c.ends_at:
            start = c.starts_at.date().isoformat() if c.starts_at else "?"
            end = c.ends_at.date().isoformat() if c.ends_at else "?"
            window = f" ({start} to {end})"
        lines.append(f"{c.title} — {c.discount_text}{window}: {c.description}")
    return "\n".join(lines)


@tool
async def save_campaign(
    competitor: str,
    title: str,
    description: str,
    discount_text: str,
    source_url: str,
    product_id: int | None = None,
    starts_at: str | None = None,
    ends_at: str | None = None,
) -> str:
    """Persist a discovered promotional campaign (a sale, discount, or
    marketing push) for a competitor. Pass product_id (from
    query_price_history's "[product_id=N]" prefix) when the campaign is
    tied to one specific product; omit it for a competitor-wide/sitewide
    promotion. starts_at/ends_at are ISO dates (e.g. 2026-09-01); omit
    either if unknown.
    """
    async with async_session_factory() as session:
        competitor_row = await _find_competitor(session, competitor)
        if competitor_row is None:
            return f"No competitor with slug {competitor!r}"

        session.add(
            Campaign(
                competitor_id=competitor_row.id,
                product_id=product_id,
                title=title,
                description=description,
                discount_text=discount_text,
                starts_at=datetime.fromisoformat(starts_at) if starts_at else None,
                ends_at=datetime.fromisoformat(ends_at) if ends_at else None,
                source_url=source_url,
            )
        )
        await session.commit()

    return "Campaign saved."


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


async def _raised_bed_products(session, competitor_id: int) -> list[Product]:
    result = await session.execute(
        select(Product).where(
            Product.competitor_id == competitor_id,
            Product.attributes["product_type"].astext.in_(RAISED_BED_TYPES),
        )
    )
    return list(result.scalars().all())


@tool
async def compare_assortment(focus_product_name: str = "") -> str:
    """Compares Gardener's Supply's raised-bed/elevated-planter assortment
    against Epic Gardening and Vego Garden — the three brands the raised-bed
    workbench tracks (see /market/raised-beds). Returns, per brand: how many
    raised-bed-family SKUs are recorded, their material/height/form
    breakdown, and median price — grounded entirely in recorded crawl data,
    no web search. Pass focus_product_name (e.g. a Gardener's Supply product
    name) to additionally get its best cross-brand comparable matches with a
    score breakdown (via app/intelligence/matching.py); leave blank for just
    the portfolio-level comparison.
    """
    async with async_session_factory() as session:
        result = await session.execute(select(Competitor).where(Competitor.slug.in_(WORKBENCH_SLUGS)))
        competitors = {c.slug: c for c in result.scalars().all()}
        if not competitors:
            return "The raised-bed workbench competitors haven't been crawled yet."

        lines = []
        all_products: dict[str, list[Product]] = {}
        for slug in WORKBENCH_SLUGS:
            competitor = competitors.get(slug)
            if competitor is None:
                continue
            products = await _raised_bed_products(session, competitor.id)
            all_products[slug] = products

            by_material: dict[str, int] = {}
            by_height: dict[str, int] = {}
            for p in products:
                material = p.attributes.get("material")
                height_band = p.attributes.get("height_band")
                if material:
                    by_material[material] = by_material.get(material, 0) + 1
                if height_band:
                    by_height[height_band] = by_height.get(height_band, 0) + 1

            prices = []
            for p in products:
                obs = (
                    await session.execute(
                        select(PriceObservation)
                        .where(PriceObservation.product_id == p.id)
                        .order_by(PriceObservation.observed_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if obs and obs.price is not None:
                    prices.append(obs.price)
            median_price = sorted(prices)[len(prices) // 2] if prices else None

            material_summary = ", ".join(f"{k}={v}" for k, v in sorted(by_material.items(), key=lambda kv: -kv[1]))
            height_summary = ", ".join(f"{k}={v}" for k, v in sorted(by_height.items(), key=lambda kv: -kv[1]))
            lines.append(
                f"{competitor.name} ({slug}): {len(products)} raised-bed/planter SKUs, "
                f"median price {median_price if median_price is not None else 'unknown'}. "
                f"Material breakdown: {material_summary or 'no data'}. "
                f"Height breakdown: {height_summary or 'no data'}."
            )

        if focus_product_name:
            target = None
            for products in all_products.values():
                for p in products:
                    if focus_product_name.lower() in p.name.lower():
                        target = p
                        break
                if target:
                    break
            if target is None:
                lines.append(f"\nNo product matching {focus_product_name!r} found among these three brands.")
            else:
                candidates = [
                    (p.id, p.attributes, p.name)
                    for products in all_products.values()
                    for p in products
                ]
                matches = find_comparables(target.id, target.attributes, target.name, candidates, limit=5)
                lines.append(f"\nClosest matches to {target.name!r}:")
                for m in matches:
                    lines.append(
                        f"  score={m.score} confidence={m.confidence} matched={m.matched_fields} "
                        f"missing={m.missing_fields} product_id={m.product_id}"
                    )

        return "\n".join(lines)
