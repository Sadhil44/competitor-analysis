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

from datetime import datetime, timedelta, timezone

from app.agent.tools import (
    list_recent_campaigns,
    list_recent_developments,
    list_recent_price_changes,
    query_price_history,
    search_campaigns,
)
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


class TestCrossCompanyTools:
    """Regression coverage for the actual reported bug: every per-company
    tool (query_price_history, search_developments, search_campaigns)
    requires a single named competitor slug, so a question that spans
    multiple or unnamed companies ("who's running promotions right now")
    had nothing to call and fell back to web_search even when other tracked
    companies had real recorded data. These three tools check every tracked
    company at once instead.
    """

    async def test_list_recent_campaigns_finds_campaign_without_naming_the_competitor(
        self, db_session, competitor_factory
    ):
        competitor = await competitor_factory(name="Zzyxquil Co")
        db_session.add(
            Campaign(
                competitor_id=competitor.id,
                title="Zzyxquil Spring Sale",
                description="Sitewide",
                discount_text="15% off",
                source_url="https://example.com",
            )
        )
        await db_session.commit()

        # High limit: this runs against the real dev DB (see conftest.py),
        # whose own recent campaigns could otherwise push this test's row
        # past the default limit.
        result = await list_recent_campaigns.ainvoke({"limit": 1000})
        assert "Zzyxquil Spring Sale" in result
        assert "Zzyxquil Co" in result

    async def test_list_recent_campaigns_filters_by_product_query(self, db_session, competitor_factory):
        competitor = await competitor_factory(name="Zzyxquil Co")
        product = Product(competitor_id=competitor.id, name="Zzyxquil Cedar Potting Bench", url="")
        db_session.add(product)
        await db_session.flush()
        db_session.add(
            Campaign(
                competitor_id=competitor.id,
                product_id=product.id,
                title="Bench Sale",
                description="20% off",
                discount_text="20% off",
                source_url="https://example.com",
            )
        )
        db_session.add(
            Campaign(
                competitor_id=competitor.id,
                title="Unrelated Seed Sale",
                description="10% off",
                discount_text="10% off",
                source_url="https://example.com",
            )
        )
        await db_session.commit()

        result = await list_recent_campaigns.ainvoke({"product_query": "workbench", "limit": 1000})
        assert "Bench Sale" in result
        assert "Unrelated Seed Sale" not in result

    async def test_list_recent_developments_across_companies_without_a_query(self, db_session, competitor_factory):
        from app.models import Development

        competitor = await competitor_factory(name="Zzyxquil Co")
        db_session.add(
            Development(
                competitor_id=competitor.id,
                title="Zzyxquil raises Series B",
                summary="Funding round",
                url="https://example.com",
                category="funding",
                event_date=datetime.now(timezone.utc).replace(tzinfo=None),
                embedding=[0.0] * 1024,
            )
        )
        await db_session.commit()

        result = await list_recent_developments.ainvoke({})
        assert "Zzyxquil raises Series B" in result
        assert "Zzyxquil Co" in result

    async def test_list_recent_price_changes_finds_moves_across_companies(self, db_session, competitor_factory):
        competitor = await competitor_factory(name="Zzyxquil Co")
        product = Product(competitor_id=competitor.id, name="Zzyxquil Raised Bed", url="")
        db_session.add(product)
        await db_session.flush()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db_session.add_all(
            [
                PriceObservation(
                    product_id=product.id, price="100.00", currency="USD", in_stock=True,
                    source="scheduled_crawl", observed_at=now - timedelta(days=5),
                ),
                PriceObservation(
                    product_id=product.id, price="80.00", currency="USD", in_stock=True,
                    source="scheduled_crawl", observed_at=now,
                ),
            ]
        )
        await db_session.commit()

        # limit set high: this runs against the real dev DB (see conftest.py),
        # which can have its own large real price swings ranking above this
        # test's small one — a high limit keeps the assertion about whether
        # this move is found at all, not where it ranks among real data.
        result = await list_recent_price_changes.ainvoke({"days": 14, "min_pct_change": 5.0, "limit": 1000})
        assert "Zzyxquil Co" in result
        assert "Zzyxquil Raised Bed" in result
        assert "down 20.0%" in result

    async def test_list_recent_price_changes_ignores_placeholder_prices_below_floor(
        self, db_session, competitor_factory
    ):
        """Regression for a real data-quality bug: a $1 placeholder/error
        price observation merged with a real price must never be reported
        as a legitimate price move (a fake +99,899% swing was surfaced
        live before this floor was added)."""
        competitor = await competitor_factory(name="Zzyxquil Co")
        product = Product(competitor_id=competitor.id, name="Zzyxquil Raised Bed", url="")
        db_session.add(product)
        await db_session.flush()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db_session.add_all(
            [
                PriceObservation(
                    product_id=product.id, price="1.00", currency="USD", in_stock=True,
                    source="scheduled_crawl", observed_at=now - timedelta(days=1),
                ),
                PriceObservation(
                    product_id=product.id, price="999.99", currency="USD", in_stock=True,
                    source="scheduled_crawl", observed_at=now,
                ),
            ]
        )
        await db_session.commit()

        result = await list_recent_price_changes.ainvoke({"days": 14, "min_pct_change": 5.0})
        assert "Zzyxquil Raised Bed" not in result
