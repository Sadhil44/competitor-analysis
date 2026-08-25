"""Tests for app/agent/tools/__init__.py's product-name matching —
query_price_history and search_campaigns used to filter on a literal
Product.name.ilike(f"%{product_query}%") substring, which silently found
nothing for a real, in-scope query like "workbench" when the recorded
product is actually named "Cedar Potting Bench" (neither string is a
substring of the other) -- the agent then reported "no data" for a
competitor that really was tracked. Regression-tested here directly against
the tools, not just app/intelligence/text.py's pure matching function, so a
future refactor of the DB-querying half can't silently reintroduce it.
"""

from datetime import datetime, timezone

from app.agent.tools import query_price_history, search_campaigns
from app.models import Campaign, PriceObservation, Product


async def _make_product_with_price(db_session, competitor_factory, name: str, price: str) -> Product:
    competitor = await competitor_factory()
    product = Product(competitor_id=competitor.id, name=name, url="")
    db_session.add(product)
    await db_session.flush()
    db_session.add(
        PriceObservation(
            product_id=product.id,
            price=price,
            currency="USD",
            in_stock=True,
            source="scheduled_crawl",
            observed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
    await db_session.commit()
    return product, competitor


async def test_query_price_history_matches_workbench_against_bench_product(db_session, competitor_factory):
    product, competitor = await _make_product_with_price(
        db_session, competitor_factory, "Zzyxquil Cedar Potting Bench", "199.99"
    )

    result = await query_price_history.ainvoke(
        {"competitor": competitor.slug, "product_query": "workbench", "days": 3650}
    )
    assert f"[product_id={product.id}]" in result
    assert "199.99" in result


async def test_query_price_history_still_matches_literal_substring(db_session, competitor_factory):
    product, competitor = await _make_product_with_price(
        db_session, competitor_factory, "Zzyxquil Raised Garden Bed", "89.99"
    )

    result = await query_price_history.ainvoke(
        {"competitor": competitor.slug, "product_query": "raised bed", "days": 3650}
    )
    assert f"[product_id={product.id}]" in result


async def test_query_price_history_unrelated_query_finds_nothing(db_session, competitor_factory):
    _, competitor = await _make_product_with_price(
        db_session, competitor_factory, "Zzyxquil Cedar Potting Bench", "199.99"
    )

    result = await query_price_history.ainvoke(
        {"competitor": competitor.slug, "product_query": "flibbertigibbet", "days": 3650}
    )
    assert result == "No matching price history found."


async def test_search_campaigns_matches_workbench_against_bench_product(db_session, competitor_factory):
    product, competitor = await _make_product_with_price(
        db_session, competitor_factory, "Zzyxquil Cedar Potting Bench", "199.99"
    )
    campaign = Campaign(
        competitor_id=competitor.id,
        product_id=product.id,
        title="Zzyxquil Bench Sale",
        description="20% off",
        discount_text="20% off",
        source_url="https://example.com",
    )
    db_session.add(campaign)
    await db_session.commit()

    result = await search_campaigns.ainvoke({"competitor": competitor.slug, "product_query": "workbench"})
    assert "Zzyxquil Bench Sale" in result
