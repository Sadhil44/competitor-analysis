from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Competitor, PriceObservation, Product
from app.schemas.competitor import CompetitorRead
from app.schemas.product import ProductRead

router = APIRouter(prefix="/competitors", tags=["competitors"])


@router.get("", response_model=list[CompetitorRead])
async def list_competitors(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Competitor))
    return result.scalars().all()


@router.get("/{slug}", response_model=CompetitorRead)
async def get_competitor(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Competitor).where(Competitor.slug == slug))
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise HTTPException(status_code=404, detail=f"No competitor with slug {slug!r}")
    return competitor


@router.get("/{slug}/products", response_model=list[ProductRead])
async def list_competitor_products(
    slug: str, response: Response, limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)
):
    # Some own-brand competitors (e.g. gardeners-supply-retail) have 30K+
    # products from the feed import, and the scraping pipeline now tracks
    # a competitor's full catalog rather than one category — capped by
    # default so this stays a cheap request; callers page through the rest
    # via `offset`. Total count goes in a response header (X-Total-Count)
    # rather than changing the response body shape, so existing callers
    # that just want `limit` products unpaginated are unaffected.
    result = await db.execute(select(Competitor).where(Competitor.slug == slug))
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise HTTPException(status_code=404, detail=f"No competitor with slug {slug!r}")

    total = (
        await db.execute(select(func.count(Product.id)).where(Product.competitor_id == competitor.id))
    ).scalar_one()
    response.headers["X-Total-Count"] = str(total)

    result = await db.execute(
        select(Product)
        .where(Product.competitor_id == competitor.id)
        .order_by(Product.name)
        .offset(offset)
        .limit(limit)
    )
    products = result.scalars().all()

    # One extra query for every product's latest observation (DISTINCT ON,
    # not N+1) — this is what actually makes the price show up on the
    # dashboard's product list, which it didn't before.
    product_ids = [p.id for p in products]
    latest_by_product: dict[int, PriceObservation] = {}
    if product_ids:
        latest_result = await db.execute(
            select(PriceObservation)
            .where(PriceObservation.product_id.in_(product_ids))
            .order_by(PriceObservation.product_id, PriceObservation.observed_at.desc())
            .distinct(PriceObservation.product_id)
        )
        latest_by_product = {obs.product_id: obs for obs in latest_result.scalars().all()}

    results = []
    for product in products:
        obs = latest_by_product.get(product.id)
        read = ProductRead.model_validate(product)
        read.latest_price = obs.price if obs else None
        read.currency = obs.currency if obs else None
        read.in_stock = obs.in_stock if obs else None
        results.append(read)
    return results
