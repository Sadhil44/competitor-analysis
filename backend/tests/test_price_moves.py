"""Tests for app/intelligence/price_moves.py's defensive guards. Each guard
here is a direct regression for a real bad result surfaced live during
testing: a $1 placeholder price read as a legitimate move, a >3000% "price
change" from two different-sized products merged under one row (see
app/scraping/ingest.py's _find_or_create_product docstring), and a delta
computed across two different currencies (Vego Garden's en-ca/CAD pages).
"""

from datetime import datetime, timedelta, timezone

from app.intelligence.price_moves import find_price_moves
from app.models import PriceObservation, Product


def _obs(product_id: int, price: str, currency: str, observed_at: datetime) -> PriceObservation:
    return PriceObservation(
        product_id=product_id, price=price, currency=currency, in_stock=True,
        source="scheduled_crawl", observed_at=observed_at,
    )


async def _make_product(db_session, competitor) -> Product:
    product = Product(competitor_id=competitor.id, name="Zzyxquil Item", url="")
    db_session.add(product)
    await db_session.flush()
    return product


async def test_finds_a_real_move(db_session, competitor_factory):
    competitor = await competitor_factory(name="Zzyxquil Co")
    product = await _make_product(db_session, competitor)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add_all([_obs(product.id, "100.00", "USD", now - timedelta(days=5)), _obs(product.id, "80.00", "USD", now)])
    await db_session.commit()

    moves = await find_price_moves(db_session, days=14, min_pct_change=5.0, limit=1000)
    assert any(m.product_id == product.id and round(m.pct_change, 1) == -20.0 for m in moves)


async def test_excludes_move_below_price_floor(db_session, competitor_factory):
    competitor = await competitor_factory(name="Zzyxquil Co")
    product = await _make_product(db_session, competitor)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add_all([_obs(product.id, "1.00", "USD", now - timedelta(days=1)), _obs(product.id, "999.99", "USD", now)])
    await db_session.commit()

    moves = await find_price_moves(db_session, days=14, min_pct_change=5.0, limit=1000)
    assert all(m.product_id != product.id for m in moves)


async def test_excludes_implausibly_large_move(db_session, competitor_factory):
    competitor = await competitor_factory(name="Zzyxquil Co")
    product = await _make_product(db_session, competitor)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Both endpoints clear the price floor, but a >3000% jump is the
    # merged-different-size-variant pattern, not a real price change.
    db_session.add_all([_obs(product.id, "29.95", "USD", now - timedelta(days=1)), _obs(product.id, "999.95", "USD", now)])
    await db_session.commit()

    moves = await find_price_moves(db_session, days=14, min_pct_change=5.0, limit=1000)
    assert all(m.product_id != product.id for m in moves)


async def test_excludes_cross_currency_pair(db_session, competitor_factory):
    competitor = await competitor_factory(name="Zzyxquil Co")
    product = await _make_product(db_session, competitor)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add_all([_obs(product.id, "700.00", "CAD", now - timedelta(days=1)), _obs(product.id, "500.00", "USD", now)])
    await db_session.commit()

    moves = await find_price_moves(db_session, days=14, min_pct_change=5.0, limit=1000)
    assert all(m.product_id != product.id for m in moves)


async def test_price_changes_endpoint_returns_a_real_move(db_session, competitor_factory, client):
    competitor = await competitor_factory(name="Zzyxquil Co")
    product = await _make_product(db_session, competitor)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add_all([_obs(product.id, "100.00", "USD", now - timedelta(days=5)), _obs(product.id, "80.00", "USD", now)])
    await db_session.commit()

    response = await client.get("/activity/price-changes", params={"days": 14, "min_pct_change": 5.0, "limit": 1000})
    assert response.status_code == 200
    body = response.json()
    assert any(row["product_id"] == product.id and row["competitor_slug"] == competitor.slug for row in body)


async def test_excludes_moves_below_min_pct_change(db_session, competitor_factory):
    competitor = await competitor_factory(name="Zzyxquil Co")
    product = await _make_product(db_session, competitor)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add_all([_obs(product.id, "100.00", "USD", now - timedelta(days=1)), _obs(product.id, "101.00", "USD", now)])
    await db_session.commit()

    moves = await find_price_moves(db_session, days=14, min_pct_change=5.0, limit=1000)
    assert all(m.product_id != product.id for m in moves)
