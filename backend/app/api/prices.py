from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import PriceObservation, Product
from app.schemas.price import PriceTrend

router = APIRouter(prefix="/products", tags=["prices"])


@router.get("/{product_id}/prices", response_model=PriceTrend)
async def get_product_price_trend(
    product_id: int,
    days: int = 90,
    db: AsyncSession = Depends(get_db),
):
    """Price history for a product, plus change detection.

    Change detection compares the two most recent observations within the
    window — not the whole history — since that's what "did the price just
    change" means in practice. `days` bounds how far back to look; our
    DateTime columns are naive (no timezone), so `since` is built as a
    naive UTC datetime to match, not an aware one.
    """
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"No product with id {product_id}")

    since = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(PriceObservation)
        .where(PriceObservation.product_id == product_id, PriceObservation.observed_at >= since)
        .order_by(PriceObservation.observed_at)
    )
    observations = result.scalars().all()

    latest_price = None
    price_change = None
    price_change_pct = None
    if observations:
        latest_price = observations[-1].price
        if len(observations) >= 2:
            previous_price = observations[-2].price
            price_change = latest_price - previous_price
            if previous_price != 0:
                price_change_pct = float(price_change / previous_price * 100)

    return PriceTrend(
        product_id=product.id,
        product_name=product.name,
        observations=observations,
        latest_price=latest_price,
        price_change=price_change,
        price_change_pct=price_change_pct,
    )
