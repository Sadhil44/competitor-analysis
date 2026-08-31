"""Tests for the first-party pricing feed importer (app/scraping/feed_import.py).

_parse_season/_parse_price are pure functions and get direct unit tests.
seed_own_brands and import_product_feed touch the DB — those are largely
regression tests for two real bugs found running the pipeline live against
Docker: (1) a re-run must not create duplicate Product rows (the
product_id_cache wasn't pre-populated from existing rows), and (2) the
ON CONFLICT dedup on PriceObservation must actually dedup (the index
predicate has to be a literal, not a bound parameter).

The DB tests use a throwaway competitor with a random, fake brand_num
(via own_brand_competitor) rather than a real config brand_num like 5
(gurneys) — that keeps fabricated test rows from ever landing on real
data, and competitor_factory (see conftest.py) cleans them up afterward.
"""

import csv
import random
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import load_own_brands_config
from app.models import Competitor, PriceObservation, Product
from app.scraping.feed_import import (
    _parse_price,
    _parse_row,
    _parse_season,
    import_product_feed,
    seed_own_brands,
)


class TestParseSeason:
    def test_fall_code(self):
        assert _parse_season("F25") == datetime(2025, 9, 1)

    def test_spring_code(self):
        assert _parse_season("S26") == datetime(2026, 3, 1)

    def test_lowercase_is_accepted(self):
        # Real source data has a handful of lowercase codes mixed in
        # ("s27", "f26") among the mostly-uppercase rest.
        assert _parse_season("s27") == datetime(2027, 3, 1)
        assert _parse_season("f26") == datetime(2026, 9, 1)

    def test_unrecognized_code_raises(self):
        with pytest.raises(ValueError):
            _parse_season("X99")


class TestParsePrice:
    def test_numeric_price(self):
        assert _parse_price("34.99") == Decimal("34.99")

    def test_null_means_not_offered(self):
        assert _parse_price("NULL") is None
        assert _parse_price("null") is None

    def test_garbage_raises(self):
        with pytest.raises(ValueError):
            _parse_price("not-a-number")


def test_parse_row_end_to_end():
    row = _parse_row(["00487", "5", "2204", " WOW ASTER PINK ", " PREMIUM ", "F25", "34.99"])
    assert row.sku == "00487"
    assert row.brand_num == 5
    assert row.name == "WOW ASTER PINK"  # whitespace stripped
    assert row.grade == "PREMIUM"
    assert row.observed_at == datetime(2025, 9, 1)
    assert row.price == Decimal("34.99")


def _write_feed_csv(tmp_path: Path, brand_num: int) -> Path:
    """A tiny, headerless feed CSV for `brand_num`: one sku across two
    seasons, plus a second sku with a NULL price (not offered that season).
    """
    path = tmp_path / "feed.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["00001", str(brand_num), "2204", "TEST PLANT", "PREMIUM", "F25", "9.99"])
        writer.writerow(["00001", str(brand_num), "2204", "TEST PLANT", "PREMIUM", "S26", "10.50"])
        writer.writerow(
            ["00002", str(brand_num), "2204", "OUT OF SEASON PLANT", "STANDARD", "F25", "NULL"]
        )
    return path


@pytest_asyncio.fixture
async def own_brand_competitor(competitor_factory) -> Competitor:
    return await competitor_factory(is_own_brand=True, brand_num=random.randint(900000, 999999))


async def test_seed_own_brands_is_idempotent(db_session):
    # Runs against the real config/own_brands.yaml — safe because
    # seed_own_brands is designed to be idempotent (match by slug, update
    # in place), so this just reaffirms one row per config entry rather
    # than creating anything new. Derived from the config itself, not a
    # hardcoded count, so this doesn't go stale every time an entry is
    # added or removed (e.g. amazon-gardeners-fulfillment and
    # gardeners-supply-retail were removed — channel/fulfillment variants
    # of gardeners-supply, not independent brands worth tracking).
    expected_count = len(load_own_brands_config())
    await seed_own_brands(db_session)
    result = await db_session.execute(select(Competitor).where(Competitor.is_own_brand))
    first_run_count = len(result.scalars().all())
    assert first_run_count == expected_count

    await seed_own_brands(db_session)
    result = await db_session.execute(select(Competitor).where(Competitor.is_own_brand))
    assert len(result.scalars().all()) == first_run_count


async def test_import_product_feed_creates_products_and_observations(
    db_session, own_brand_competitor, tmp_path
):
    csv_path = _write_feed_csv(tmp_path, own_brand_competitor.brand_num)
    await import_product_feed(db_session, csv_path)

    result = await db_session.execute(
        select(Product).where(
            Product.competitor_id == own_brand_competitor.id, Product.sku == "00001"
        )
    )
    product = result.scalar_one()
    assert product.name == "TEST PLANT"
    assert product.grade == "PREMIUM"

    result = await db_session.execute(
        select(PriceObservation).where(PriceObservation.product_id == product.id)
    )
    observations = {obs.observed_at: obs.price for obs in result.scalars().all()}
    assert observations == {
        datetime(2025, 9, 1): Decimal("9.99"),
        datetime(2026, 3, 1): Decimal("10.50"),
    }


async def test_import_product_feed_null_price_means_out_of_stock(
    db_session, own_brand_competitor, tmp_path
):
    csv_path = _write_feed_csv(tmp_path, own_brand_competitor.brand_num)
    await import_product_feed(db_session, csv_path)

    result = await db_session.execute(
        select(Product).where(
            Product.competitor_id == own_brand_competitor.id, Product.sku == "00002"
        )
    )
    product = result.scalar_one()
    result = await db_session.execute(
        select(PriceObservation).where(PriceObservation.product_id == product.id)
    )
    obs = result.scalar_one()
    assert obs.price is None
    assert obs.in_stock is False


async def test_import_product_feed_is_idempotent(db_session, own_brand_competitor, tmp_path):
    """Regression test: product_id_cache used to start empty on every call
    instead of being pre-populated from existing DB rows, so re-running the
    import on the same file silently created duplicate Product rows for
    SKUs that already existed."""
    csv_path = _write_feed_csv(tmp_path, own_brand_competitor.brand_num)
    await import_product_feed(db_session, csv_path)
    await import_product_feed(db_session, csv_path)  # re-run on the same file

    result = await db_session.execute(
        select(Product).where(
            Product.competitor_id == own_brand_competitor.id, Product.sku == "00001"
        )
    )
    assert len(result.scalars().all()) == 1

    result = await db_session.execute(
        select(PriceObservation)
        .join(Product)
        .where(Product.competitor_id == own_brand_competitor.id, Product.sku == "00001")
    )
    # Still exactly 2 observations (one per season) after two runs, not 4 —
    # this is the ON CONFLICT dedup working, not just the product-level fix.
    assert len(result.scalars().all()) == 2


async def test_import_product_feed_skips_unmapped_brand_num_rows(db_session, tmp_path):
    """Regression test: a brand_num with no config/own_brands.yaml entry
    (e.g. real brand_num 66/72 — Amazon-fulfillment/retail-restock channels
    deliberately left unmapped, see own_brands.yaml) used to raise and abort
    the ENTIRE import on the first such row. A fresh database has no rows
    from those channels yet, so the very first real-data import run hit
    this immediately. Skipping the row is correct: nothing was ever meant
    to track that channel.
    """
    unmapped_brand_num = random.randint(900000, 999999)
    distinctive_sku = f"zzyx-{unmapped_brand_num}"
    csv_path = tmp_path / "feed.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(
            [distinctive_sku, str(unmapped_brand_num), "2204", "TEST PLANT", "PREMIUM", "F25", "9.99"]
        )

    await import_product_feed(db_session, csv_path)  # must not raise

    result = await db_session.execute(select(Product).where(Product.sku == distinctive_sku))
    assert result.scalars().first() is None
