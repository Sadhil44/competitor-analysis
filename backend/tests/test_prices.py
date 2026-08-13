"""Tests for the price-trend endpoint's change-detection logic
(app/api/prices.py) — mostly the edge cases around missing/None prices,
since price is nullable (out-of-stock/unlisted items show no price).
"""

from datetime import datetime, timedelta
from decimal import Decimal

from app.models import PriceObservation, Product

# Relative to "now" rather than a fixed date — the endpoint defaults to a
# 90-day lookback window (app/api/prices.py), so a hardcoded date like
# datetime(2026, 1, 1) silently falls outside that window and gets
# filtered out once enough real time has passed since the test was written.
_TWO_DAYS_AGO = datetime.now() - timedelta(days=2)
_ONE_DAY_AGO = datetime.now() - timedelta(days=1)


async def _make_product(db_session, competitor_factory) -> Product:
    competitor = await competitor_factory()
    product = Product(competitor_id=competitor.id, name="Test Product", url="")
    db_session.add(product)
    await db_session.flush()
    return product


async def test_no_observations_returns_none_fields(client, db_session, competitor_factory):
    product = await _make_product(db_session, competitor_factory)
    await db_session.commit()

    response = await client.get(f"/products/{product.id}/prices")
    assert response.status_code == 200
    body = response.json()
    assert body["latest_price"] is None
    assert body["price_change"] is None
    assert body["price_change_pct"] is None
    assert body["observations"] == []


async def test_single_observation_has_no_change(client, db_session, competitor_factory):
    product = await _make_product(db_session, competitor_factory)
    db_session.add(
        PriceObservation(
            product=product,
            price=Decimal("10.00"),
            currency="USD",
            in_stock=True,
            source="test",
            observed_at=_TWO_DAYS_AGO,
        )
    )
    await db_session.commit()

    response = await client.get(f"/products/{product.id}/prices")
    body = response.json()
    assert Decimal(str(body["latest_price"])) == Decimal("10.00")
    assert body["price_change"] is None


async def test_price_increase_computes_change_and_pct(client, db_session, competitor_factory):
    product = await _make_product(db_session, competitor_factory)
    db_session.add_all(
        [
            PriceObservation(
                product=product,
                price=Decimal("10.00"),
                currency="USD",
                in_stock=True,
                source="test",
                observed_at=_TWO_DAYS_AGO,
            ),
            PriceObservation(
                product=product,
                price=Decimal("12.00"),
                currency="USD",
                in_stock=True,
                source="test",
                observed_at=_ONE_DAY_AGO,
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(f"/products/{product.id}/prices")
    body = response.json()
    assert Decimal(str(body["latest_price"])) == Decimal("12.00")
    assert Decimal(str(body["price_change"])) == Decimal("2.00")
    assert body["price_change_pct"] == 20.0


async def test_out_of_stock_price_is_none_and_skips_change(client, db_session, competitor_factory):
    """A None price (out-of-stock/no listing shown) shouldn't be diffed
    against a real price — there's nothing to compute a percent change from
    when one side is "no price shown" rather than an actual number."""
    product = await _make_product(db_session, competitor_factory)
    db_session.add_all(
        [
            PriceObservation(
                product=product,
                price=Decimal("10.00"),
                currency="USD",
                in_stock=True,
                source="test",
                observed_at=_TWO_DAYS_AGO,
            ),
            PriceObservation(
                product=product,
                price=None,
                currency="USD",
                in_stock=False,
                source="test",
                observed_at=_ONE_DAY_AGO,
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(f"/products/{product.id}/prices")
    body = response.json()
    assert body["latest_price"] is None
    assert body["price_change"] is None
    assert body["price_change_pct"] is None


async def test_unknown_product_returns_404(client):
    response = await client.get("/products/999999/prices")
    assert response.status_code == 404
