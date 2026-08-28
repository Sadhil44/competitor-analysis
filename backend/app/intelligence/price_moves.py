"""Cross-competitor price-move detection — shared by the agent's
list_recent_price_changes tool (app/agent/tools/__init__.py) and the
/activity/price-changes API endpoint (app/api/activity.py) so the two
surfaces (chat and dashboard) can never silently disagree about what counts
as a real price move.

Compares each product's earliest vs. latest recorded price within a window,
across every tracked company at once (not scoped to one competitor).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Competitor, PriceObservation, Product

# Nothing in this catalog is realistically priced under $3 — guards against a
# stray placeholder/error price (e.g. a $1 "notify me" or misextracted
# variant price) reading as a real, dramatic move. See app/scraping/
# ingest.py's _find_or_create_product docstring for the corruption pattern
# this was written to protect against downstream of.
PRICE_FLOOR = Decimal("3.00")

# A real sale/promotion in this catalog is realistically well under 100% —
# a move past this is far more likely two genuinely different products/
# variants merged under one Product row (confirmed live and widespread: e.g.
# same-named different-size nursery stock — a small vs. a mature plant, or a
# 1-gallon vs. a multi-gallon size tier — sharing no SKU on the source site,
# so even the ingest fix above can't separate them) than an actual price
# change. Deliberately conservative (not just "large enough to catch the
# worst cases"): surfacing "Product X's price jumped 240%" live to the exact
# audience this data is about would be actively misleading, not just noisy,
# so this filters generously rather than just deprioritizing the extreme
# tail. This is a real known gap (plant/nursery catalogs routinely reuse one
# display name across size/quantity tiers with no distinguishing SKU) that a
# threshold can only mask, not fix — see the project handoff notes.
MAX_PLAUSIBLE_PCT_CHANGE = 75.0


@dataclass
class PriceMove:
    product_id: int
    product_name: str
    product_url: str
    competitor_slug: str
    competitor_name: str
    is_own_brand: bool
    first_price: Decimal
    last_price: Decimal
    pct_change: float
    currency: str
    last_observed_at: datetime



# Preference order when a product has observations from more than one
# source (every own-brand product does: internal_feed alongside
# scheduled_crawl once it's also scraped). scheduled_crawl wins when
# present — it's the only preference chosen based on data plausibility.
_SOURCE_PREFERENCE = ("scheduled_crawl", "internal_feed")


async def find_price_moves(
    session: AsyncSession, *, days: int = 14, min_pct_change: float = 5.0, limit: int = 20
) -> list[PriceMove]:
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    # Partitioned by (product_id, source), not product_id alone — a
    # product's internal_feed observations (a seasonal wholesale/catalog
    # reference price, quarterly cadence) and its scheduled_crawl
    # observations (the live scraped retail price) are two genuinely
    # different numbers, not two points on one price timeline. Diffing
    # across them produced exactly the fake-looking move this guards
    # against live: a mid-season "$16.99, out of stock" scrape sitting
    # between two $28-29 seasonal feed entries read as a 70%+ "price move"
    # that was really just two unrelated price concepts collided.
    rn_first = func.row_number().over(
        partition_by=(PriceObservation.product_id, PriceObservation.source),
        order_by=PriceObservation.observed_at.asc(),
    ).label("rn_first")
    rn_last = func.row_number().over(
        partition_by=(PriceObservation.product_id, PriceObservation.source),
        order_by=PriceObservation.observed_at.desc(),
    ).label("rn_last")
    subq = (
        select(
            PriceObservation.product_id,
            PriceObservation.source,
            PriceObservation.price,
            PriceObservation.currency,
            PriceObservation.observed_at,
            rn_first,
            rn_last,
        )
        .where(PriceObservation.observed_at >= since, PriceObservation.price.is_not(None))
        .subquery()
    )
    endpoint_rows = (
        await session.execute(select(subq).where(or_(subq.c.rn_first == 1, subq.c.rn_last == 1)))
    ).all()

    by_product_source: dict[tuple[int, str], dict] = {}
    for row in endpoint_rows:
        entry = by_product_source.setdefault((row.product_id, row.source), {})
        if row.rn_first == 1:
            entry["first_price"] = row.price
            entry["first_at"] = row.observed_at
            entry["first_currency"] = row.currency
        if row.rn_last == 1:
            entry["last_price"] = row.price
            entry["last_at"] = row.observed_at
            entry["currency"] = row.currency

    by_product: dict[int, dict[str, dict]] = {}
    for (product_id, source), entry in by_product_source.items():
        by_product.setdefault(product_id, {})[source] = entry

    candidates: list[tuple[int, Decimal, Decimal, float, str, datetime]] = []
    chosen_source_by_product: dict[int, str] = {}
    for product_id, sources in by_product.items():
        entry = next((sources[s] for s in _SOURCE_PREFERENCE if s in sources), None)
        if entry is None:
            continue
        first_price, last_price = entry.get("first_price"), entry.get("last_price")
        if first_price is None or last_price is None or entry.get("first_at") == entry.get("last_at"):
            continue
        if first_price < PRICE_FLOOR or last_price < PRICE_FLOOR:
            continue
        # A product crawled under more than one regional storefront variant
        # (confirmed live: Vego Garden's en-ca pages price in CAD alongside
        # its USD default) can have differently-currencied observations on
        # the SAME product row — a delta across currencies isn't a price
        # move at all, just unit-mismatched noise.
        if entry.get("first_currency") and entry.get("first_currency") != entry.get("currency"):
            continue
        pct = float((last_price - first_price) / first_price * 100)
        if abs(pct) > MAX_PLAUSIBLE_PCT_CHANGE:
            continue
        if abs(pct) >= min_pct_change:
            source_name = next(s for s in _SOURCE_PREFERENCE if s in sources)
            chosen_source_by_product[product_id] = source_name
            candidates.append(
                (product_id, first_price, last_price, pct, entry.get("currency") or "USD", entry["last_at"])
            )

    if not candidates:
        return []

    # A product page that lists more than one sellable offer (e.g. a Shopify
    # product with several size/quantity variants sharing one product row —
    # confirmed live on Epic Gardening's seed listings) can have its recorded
    # price bounce between two real, different offer prices across crawls
    # instead of settling on one — e.g. $3.49, $3.49, $5.99, $5.99, $3.49,
    # $5.99. That reads as a dramatic "price move" by a first-vs-last diff,
    # but it's oscillating extraction noise, not a step change. A real price
    # change is a single step: stable at A, then stable at B — at most two
    # runs of a distinct value. More than two runs means the value bounced
    # back to an earlier price at least once, which a genuine one-time
    # change never does.
    history_rows = (
        await session.execute(
            select(
                PriceObservation.product_id, PriceObservation.source,
                PriceObservation.price, PriceObservation.observed_at,
            )
            .where(
                PriceObservation.product_id.in_([c[0] for c in candidates]),
                PriceObservation.observed_at >= since,
                PriceObservation.price.is_not(None),
            )
            .order_by(PriceObservation.product_id, PriceObservation.observed_at)
        )
    ).all()
    history_by_product: dict[int, list[tuple[str, Decimal]]] = {}
    for product_id, source, price, _observed_at in history_rows:
        history_by_product.setdefault(product_id, []).append((source, price))

    stable_candidates = []
    for c in candidates:
        product_id = c[0]
        chosen_source = chosen_source_by_product[product_id]
        seq = [price for source, price in history_by_product.get(product_id, []) if source == chosen_source]
        runs = sum(1 for prev, curr in zip(seq, seq[1:]) if curr != prev) + (1 if seq else 0)
        if runs <= 2:
            stable_candidates.append(c)
    candidates = stable_candidates

    if not candidates:
        return []

    candidates.sort(key=lambda c: abs(c[3]), reverse=True)
    candidates = candidates[:limit]

    product_ids = [c[0] for c in candidates]
    product_rows = (
        await session.execute(
            select(Product, Competitor)
            .join(Competitor, Competitor.id == Product.competitor_id)
            .where(Product.id.in_(product_ids))
        )
    ).all()
    product_by_id = {p.id: (p, c) for p, c in product_rows}

    moves = []
    for product_id, first_price, last_price, pct, currency, last_observed_at in candidates:
        entry = product_by_id.get(product_id)
        if entry is None:
            continue
        product, competitor = entry
        moves.append(
            PriceMove(
                product_id=product.id,
                product_name=product.name,
                product_url=product.url,
                competitor_slug=competitor.slug,
                competitor_name=competitor.name,
                is_own_brand=competitor.is_own_brand,
                first_price=first_price,
                last_price=last_price,
                pct_change=pct,
                currency=currency,
                last_observed_at=last_observed_at,
            )
        )
    return moves
