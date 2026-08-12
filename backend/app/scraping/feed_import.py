"""Bulk import of the first-party pricing feed (our own brands).

Unlike ingest.py (which discovers products by scraping a competitor's live
site), this reads a CSV export from our internal systems: one row per
(brand, sku, season), covering Spring Hill Nurseries, Gurney's, Breck's,
K. van Bourgondien, and Gardener's Supply's catalog/retail channels. The
CSV has no header row and columns are positional:

    sku, brand_num, category_code, name, grade, season, price

`brand_num` is resolved against config/own_brands.yaml (see
seed_own_brands). `season` is a catalog period like "F25" or "S26"
(Fall/Spring of 20YY) rather than a real timestamp — it's converted to a
representative date (see _parse_season) so it slots into the same
observed_at time series as scraped observations. A missing price ("NULL"
in the source) means the item wasn't offered that season, mirrored the
same way scraped out-of-stock listings are: price=None, in_stock=False.

Known limitation: feed-imported products are matched by (competitor_id,
sku), while scraped products are matched by (competitor_id, name) — see
ingest.py. For a brand like Gurney's that has both a scraped competitor row
and feed data, the same real-world product currently ends up as two
separate Product rows (one per source) rather than being reconciled into
one. Fine for now; reconciling them would need fuzzy name/sku matching,
which is its own piece of work.
"""

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import load_own_brands_config
from app.models import Competitor, PriceObservation, Product

FEED_SOURCE = "internal_feed"
FEED_CURRENCY = "USD"
# asyncpg hard-caps a single prepared statement at 32767 bound parameters.
# Each PriceObservation row binds 7 params, so 5000 rows/batch (35000 params)
# blew past that; 2000 rows (14000 params) leaves real headroom.
IMPORT_BATCH_SIZE = 2000

_SEASON_RE = re.compile(r"^([FS])(\d{2})$", re.IGNORECASE)


def _parse_season(season: str) -> datetime:
    """"F25" -> Fall 2025 -> 2025-09-01; "S26" -> Spring 2026 -> 2026-03-01.

    A catalog period, not a real event timestamp — September 1 / March 1
    are arbitrary but consistent stand-ins that preserve chronological
    ordering across seasons. Case-insensitive: the source data has a
    handful of lowercase codes ("s27", "f26") mixed in with the rest.
    """
    match = _SEASON_RE.match(season.strip())
    if match is None:
        raise ValueError(f"Unrecognized season code: {season!r}")
    period, year_suffix = match.group(1).upper(), int(match.group(2))
    year = 2000 + year_suffix
    month, day = (3, 1) if period == "S" else (9, 1)
    return datetime(year, month, day)


def _parse_price(raw: str) -> Decimal | None:
    if raw.strip().upper() == "NULL":
        return None
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"Unparseable price: {raw!r}") from exc


@dataclass
class FeedRow:
    sku: str
    brand_num: int
    category: str
    name: str
    grade: str
    observed_at: datetime
    price: Decimal | None


def _parse_row(raw_row: list[str]) -> FeedRow:
    sku, brand_num, category, name, grade, season, price = raw_row
    return FeedRow(
        sku=sku.strip(),
        brand_num=int(brand_num),
        category=category.strip(),
        name=name.strip(),
        grade=grade.strip(),
        observed_at=_parse_season(season),
        price=_parse_price(price),
    )


async def seed_own_brands(session: AsyncSession) -> None:
    """Sync config/own_brands.yaml into the competitors table.

    Matches by slug first (so brand_num 5's "gurneys" entry updates the
    existing scraped Gurney's competitor row instead of duplicating it),
    then falls back to creating a new row. Safe to re-run.
    """
    for entry in load_own_brands_config():
        result = await session.execute(select(Competitor).where(Competitor.slug == entry.slug))
        competitor = result.scalar_one_or_none()
        if competitor is None:
            competitor = Competitor(
                slug=entry.slug,
                name=entry.name,
                website_url=entry.website_url,
                notes=entry.notes,
            )
            session.add(competitor)
        competitor.is_own_brand = True
        competitor.brand_num = entry.brand_num
    await session.commit()


async def import_product_feed(session: AsyncSession, csv_path: Path) -> None:
    """Load the positional, headerless CSV feed described in this module's
    docstring, upserting Product rows (matched on (competitor_id, sku)) and
    appending PriceObservation rows for each (sku, season) reading.

    Assumes seed_own_brands has already run — raises if a row's brand_num
    isn't a known own-brand.
    """
    result = await session.execute(
        select(Competitor.brand_num, Competitor.id).where(Competitor.brand_num.is_not(None))
    )
    competitor_id_by_brand_num: dict[int, int] = dict(result.all())

    # Pre-populate from products already in the DB (from this competitor set)
    # — without this, a second run (or a run picking up after an earlier one)
    # can't tell an existing product from a new one and creates duplicates.
    existing = await session.execute(
        select(Product.competitor_id, Product.sku, Product.id).where(
            Product.competitor_id.in_(competitor_id_by_brand_num.values()),
            Product.sku.is_not(None),
        )
    )
    product_id_cache: dict[tuple[int, str], int] = {
        (competitor_id, sku): product_id for competitor_id, sku, product_id in existing
    }

    batch: list[FeedRow] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for raw_row in csv.reader(f):
            batch.append(_parse_row(raw_row))
            if len(batch) >= IMPORT_BATCH_SIZE:
                await _import_batch(session, batch, competitor_id_by_brand_num, product_id_cache)
                batch = []
    if batch:
        await _import_batch(session, batch, competitor_id_by_brand_num, product_id_cache)


async def _import_batch(
    session: AsyncSession,
    rows: list[FeedRow],
    competitor_id_by_brand_num: dict[int, int],
    product_id_cache: dict[tuple[int, str], int],
) -> None:
    missing: dict[tuple[int, str], FeedRow] = {}
    for row in rows:
        if row.brand_num not in competitor_id_by_brand_num:
            raise ValueError(
                f"brand_num {row.brand_num} has no matching competitor — "
                "run seed_own_brands first or add it to config/own_brands.yaml"
            )
        competitor_id = competitor_id_by_brand_num[row.brand_num]
        key = (competitor_id, row.sku)
        if key not in product_id_cache and key not in missing:
            missing[key] = row

    if missing:
        new_products = [
            Product(
                competitor_id=competitor_id,
                sku=row.sku,
                name=row.name,
                grade=row.grade,
                category=row.category,
                url="",
            )
            for (competitor_id, _sku), row in missing.items()
        ]
        session.add_all(new_products)
        await session.flush()
        for (competitor_id, sku), product in zip(missing.keys(), new_products):
            product_id_cache[(competitor_id, sku)] = product.id

    observation_rows = []
    for row in rows:
        competitor_id = competitor_id_by_brand_num[row.brand_num]
        product_id = product_id_cache[(competitor_id, row.sku)]
        observation_rows.append(
            {
                "product_id": product_id,
                "price": row.price,
                "currency": FEED_CURRENCY,
                "in_stock": row.price is not None,
                "promo_text": "",
                "observed_at": row.observed_at,
                "source": FEED_SOURCE,
            }
        )

    stmt = pg_insert(PriceObservation).values(observation_rows)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["product_id", "observed_at", "source"],
        # Must be a literal, not a bound parameter — Postgres matches a
        # partial index's ON CONFLICT inference predicate by expression
        # structure, and a bind param never structurally matches the
        # literal `source = 'internal_feed'` predicate the index was
        # created with (see the migration), even though the values agree
        # at runtime.
        index_where=text(f"source = '{FEED_SOURCE}'"),
    )
    await session.execute(stmt)
    await session.commit()
