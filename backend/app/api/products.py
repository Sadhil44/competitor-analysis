from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.intelligence.text import name_matches_query as _name_matches_query
from app.intelligence.text import significant_keywords as _significant_keywords
from app.models import Campaign, Competitor, PriceObservation, Product
from app.schemas.campaign import CampaignRead
from app.schemas.comparable import ComparableProduct
from app.schemas.product import ProductRead

router = APIRouter(prefix="/products", tags=["products"])


async def _hydrate_with_latest_price(
    db: AsyncSession, rows: list[tuple[Product, Competitor]]
) -> list[ComparableProduct]:
    matched_product_ids = [product.id for product, _ in rows]
    latest_by_product: dict[int, PriceObservation] = {}
    if matched_product_ids:
        latest_result = await db.execute(
            select(PriceObservation)
            .where(PriceObservation.product_id.in_(matched_product_ids))
            .order_by(PriceObservation.product_id, PriceObservation.observed_at.desc())
            .distinct(PriceObservation.product_id)
        )
        latest_by_product = {obs.product_id: obs for obs in latest_result.scalars().all()}

    results = []
    for product, competitor in rows:
        obs = latest_by_product.get(product.id)
        results.append(
            ComparableProduct(
                id=product.id,
                name=product.name,
                url=product.url,
                competitor_id=competitor.id,
                competitor_slug=competitor.slug,
                competitor_name=competitor.name,
                latest_price=obs.price if obs else None,
                currency=obs.currency if obs else None,
            )
        )
    return results


async def _fallback_keyword_scan(
    db: AsyncSession, keywords: list[str], *, exclude_competitor_id: int | None, limit: int
) -> list[ComparableProduct]:
    """Bidirectional keyword-overlap match (see app/intelligence/text.py) as
    a fallback when to_tsquery finds nothing — catches a query like
    "workbench" against a product actually named "Cedar Potting Bench",
    which stemmed full-text search can't (they don't share a lexeme). Only
    runs on a zero-result tsquery search, so the full-table scan this
    requires (no index supports the substring check) stays rare rather than
    being paid on every request.
    """
    stmt = select(Product, Competitor).join(Competitor, Competitor.id == Product.competitor_id)
    if exclude_competitor_id is not None:
        stmt = stmt.where(Product.competitor_id != exclude_competitor_id)
    all_rows = (await db.execute(stmt)).all()

    matched = [(row.Product, row.Competitor) for row in all_rows if _name_matches_query(row.Product.name, keywords)]
    return await _hydrate_with_latest_price(db, matched[:limit])


async def _search_by_keywords(
    db: AsyncSession, keywords: list[str], *, exclude_competitor_id: int | None, limit: int
) -> list[ComparableProduct]:
    """Postgres full-text search over Product.name, ranked by relevance —
    the shared core behind both "find comparable products for this one"
    (excludes the source product's own competitor) and open-ended
    cross-competitor search (no exclusion). ORs the keywords together, not
    ANDs them — plainto_tsquery's default AND semantics meant a 5-word name
    required every one of those words to appear in a candidate name, which
    silently excluded real matches missing just one word.
    """
    if not keywords:
        return []

    query = func.to_tsquery("english", " | ".join(keywords))
    name_vector = func.to_tsvector("english", Product.name)
    rank = func.ts_rank(name_vector, query)

    stmt = (
        select(Product, Competitor, rank.label("rank"))
        .join(Competitor, Competitor.id == Product.competitor_id)
        .where(name_vector.op("@@")(query))
        .order_by(rank.desc())
        .limit(limit)
    )
    if exclude_competitor_id is not None:
        stmt = stmt.where(Product.competitor_id != exclude_competitor_id)
    rows = (await db.execute(stmt)).all()

    if not rows:
        return await _fallback_keyword_scan(
            db, keywords, exclude_competitor_id=exclude_competitor_id, limit=limit
        )

    return await _hydrate_with_latest_price(db, [(row.Product, row.Competitor) for row in rows])


@router.get("/search", response_model=list[ComparableProduct])
async def search_products(q: str, limit: int = 20, db: AsyncSession = Depends(get_db)):
    """Cross-competitor product search by name/keyword — the same
    full-text-search machinery behind "comparable products", opened up as
    a standalone search that doesn't require starting from an existing
    product. Registered ahead of /{product_id} so "search" isn't swallowed
    as a product_id path param.
    """
    return await _search_by_keywords(db, _significant_keywords(q), exclude_competitor_id=None, limit=limit)


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    # AsyncSession.get() is the shorthand for a primary-key lookup — simpler
    # than select(Product).where(Product.id == product_id) for this case.
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"No product with id {product_id}")
    return product


@router.get("/{product_id}/campaigns", response_model=list[CampaignRead])
async def get_product_campaigns(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"No product with id {product_id}")

    result = await db.execute(
        select(Campaign)
        .where(Campaign.product_id == product_id)
        .order_by(Campaign.discovered_at.desc())
    )
    return result.scalars().all()


@router.get("/{product_id}/comparable", response_model=list[ComparableProduct])
async def get_comparable_products(
    product_id: int, limit: int = 5, db: AsyncSession = Depends(get_db)
):
    """Products from OTHER competitors whose names share significant words
    with this one, ranked by relevance — see _search_by_keywords."""
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"No product with id {product_id}")

    return await _search_by_keywords(
        db, _significant_keywords(product.name), exclude_competitor_id=product.competitor_id, limit=limit
    )
