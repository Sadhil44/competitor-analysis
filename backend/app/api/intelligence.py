"""Raised-bed market comparison endpoints — the one Wednesday-demo-specific
API surface in this codebase. Everything served here is computed from the
same Product/PriceObservation/CrawlRun tables every other endpoint reads,
filtered to the three demo competitors and gated to actual raised-bed/
elevated-planter products via Product.attributes["product_type"] (see
app/intelligence/normalizer.py for how that gets populated, and
app/intelligence/matching.py for the comparison scoring).
"""

from datetime import datetime, timezone
from decimal import Decimal
from statistics import median

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.intelligence.matching import find_comparables
from app.models import Competitor, CrawlRun, PriceObservation, Product
from app.schemas.intelligence import (
    BrandSummary,
    ComparableMatch,
    MatrixCell,
    RaisedBedMatrix,
    RaisedBedProduct,
    RaisedBedSummary,
)

router = APIRouter(prefix="/intelligence/raised-beds", tags=["intelligence"])

# The three competitors this workbench compares — see config/competitors.yaml
# for their crawl targets; this is just which of the tracked competitors
# this specific workbench is scoped to (each is crawled for its full
# catalog, not only raised beds — see backend/scripts/crawl_demo_scope.py).
WORKBENCH_SLUGS = ["gardeners-supply", "epic-gardening", "vego-garden"]
RAISED_BED_TYPES = ("raised_bed", "elevated_planter")


async def _in_scope_products(db: AsyncSession, competitor_id: int) -> list[Product]:
    result = await db.execute(
        select(Product).where(
            Product.competitor_id == competitor_id,
            Product.attributes["product_type"].astext.in_(RAISED_BED_TYPES),
        )
    )
    return list(result.scalars().all())


async def _latest_observations(db: AsyncSession, product_ids: list[int]) -> dict[int, PriceObservation]:
    if not product_ids:
        return {}
    result = await db.execute(
        select(PriceObservation)
        .where(PriceObservation.product_id.in_(product_ids))
        .order_by(PriceObservation.product_id, PriceObservation.observed_at.desc())
        .distinct(PriceObservation.product_id)
    )
    return {obs.product_id: obs for obs in result.scalars().all()}


@router.get("/summary", response_model=RaisedBedSummary)
async def get_summary(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Competitor).where(Competitor.slug.in_(WORKBENCH_SLUGS)))
    competitors = {c.slug: c for c in result.scalars().all()}

    brands = []
    for slug in WORKBENCH_SLUGS:
        competitor = competitors.get(slug)
        if competitor is None:
            continue
        products = await _in_scope_products(db, competitor.id)
        observations = await _latest_observations(db, [p.id for p in products])

        prices = [obs.price for obs in observations.values() if obs.price is not None]
        in_stock_count = sum(1 for obs in observations.values() if obs.in_stock)
        promo_count = sum(1 for obs in observations.values() if obs.promo_text)

        latest_crawl = (
            await db.execute(
                select(CrawlRun)
                .where(CrawlRun.competitor_id == competitor.id)
                .order_by(CrawlRun.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        # Shares are of products with a recorded observation, not of every
        # in-scope product — a product with no observation yet has neither
        # a known price nor a known stock/promo state, so it can't count
        # against either the "in stock" or "out of stock" side.
        denom = len(observations) or 1
        brands.append(
            BrandSummary(
                competitor_slug=slug,
                competitor_name=competitor.name,
                is_own_brand=competitor.is_own_brand,
                product_count=len(products),
                median_price=Decimal(str(median(prices))) if prices else None,
                promo_share=promo_count / denom,
                in_stock_share=in_stock_count / denom,
                last_crawled_at=latest_crawl.started_at if latest_crawl else None,
                last_crawl_status=latest_crawl.status if latest_crawl else None,
                pages_fetched=latest_crawl.pages_fetched if latest_crawl else None,
            )
        )

    return RaisedBedSummary(
        generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        scope_note=(
            "Scoped to products classified as raised_bed or elevated_planter "
            "by app/intelligence/normalizer.py's deterministic text parsing "
            "— not necessarily every raised bed these competitors sell, "
            "and not a manually curated list."
        ),
        brands=brands,
    )


@router.get("/products", response_model=list[RaisedBedProduct])
async def get_products(competitor_slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Competitor).where(Competitor.slug == competitor_slug))
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise HTTPException(status_code=404, detail=f"No competitor with slug {competitor_slug!r}")

    products = await _in_scope_products(db, competitor.id)
    observations = await _latest_observations(db, [p.id for p in products])

    results = []
    for product in sorted(products, key=lambda p: p.name):
        obs = observations.get(product.id)
        results.append(
            RaisedBedProduct(
                id=product.id,
                name=product.name,
                url=product.url,
                latest_price=obs.price if obs else None,
                currency=obs.currency if obs else None,
                in_stock=obs.in_stock if obs else None,
                material=product.attributes.get("material"),
                height_band=product.attributes.get("height_band"),
                form=product.attributes.get("form"),
                footprint=product.attributes.get("footprint"),
            )
        )
    return results


@router.get("/matrix", response_model=RaisedBedMatrix)
async def get_matrix(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Competitor).where(Competitor.slug.in_(WORKBENCH_SLUGS)))
    competitor_slugs = {c.id: c.slug for c in result.scalars().all()}

    cells: dict[tuple[str, str, str, str], int] = {}
    excluded = 0
    for competitor_id, slug in competitor_slugs.items():
        for product in await _in_scope_products(db, competitor_id):
            material = product.attributes.get("material")
            height_band = product.attributes.get("height_band")
            form = product.attributes.get("form")
            if not (material and height_band and form):
                excluded += 1
                continue
            key = (slug, material, height_band, form)
            cells[key] = cells.get(key, 0) + 1

    return RaisedBedMatrix(
        cells=[
            MatrixCell(competitor_slug=slug, material=material, height_band=height_band, form=form, count=count)
            for (slug, material, height_band, form), count in cells.items()
        ],
        excluded_incomplete_count=excluded,
    )


@router.get("/comparables", response_model=list[ComparableMatch])
async def get_comparables(product_id: int, limit: int = 10, db: AsyncSession = Depends(get_db)):
    target = await db.get(Product, product_id)
    if target is None:
        raise HTTPException(status_code=404, detail=f"No product with id {product_id}")

    result = await db.execute(select(Competitor).where(Competitor.slug.in_(WORKBENCH_SLUGS)))
    competitor_by_id = {c.id: c for c in result.scalars().all()}

    candidates: list[tuple[int, dict, str]] = []
    product_by_id: dict[int, Product] = {}
    for competitor_id in competitor_by_id:
        for product in await _in_scope_products(db, competitor_id):
            candidates.append((product.id, product.attributes, product.name))
            product_by_id[product.id] = product

    matches = find_comparables(target.id, target.attributes, target.name, candidates, limit=limit)

    observations = await _latest_observations(db, [m.product_id for m in matches])

    results = []
    for match in matches:
        product = product_by_id[match.product_id]
        competitor = competitor_by_id[product.competitor_id]
        obs = observations.get(product.id)
        results.append(
            ComparableMatch(
                product_id=product.id,
                name=product.name,
                url=product.url,
                competitor_slug=competitor.slug,
                competitor_name=competitor.name,
                latest_price=obs.price if obs else None,
                currency=obs.currency if obs else None,
                score=match.score,
                confidence=match.confidence,
                matched_fields=match.matched_fields,
                missing_fields=match.missing_fields,
            )
        )
    return results
