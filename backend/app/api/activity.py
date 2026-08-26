"""Cross-competitor activity endpoints — not scoped to one company or one
product category (contrast app/api/intelligence.py's raised-bed-specific
comparison). Currently just price moves; a natural place to add cross-
competitor campaigns/developments endpoints if the dashboard needs them.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.intelligence.price_moves import find_price_moves
from app.schemas.intelligence import PriceMoveOut

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("/price-changes", response_model=list[PriceMoveOut])
async def get_price_changes(
    days: int = 14,
    min_pct_change: float = 5.0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    moves = await find_price_moves(db, days=days, min_pct_change=min_pct_change, limit=limit)
    return [
        PriceMoveOut(
            product_id=m.product_id,
            product_name=m.product_name,
            product_url=m.product_url,
            competitor_slug=m.competitor_slug,
            competitor_name=m.competitor_name,
            is_own_brand=m.is_own_brand,
            first_price=m.first_price,
            last_price=m.last_price,
            pct_change=m.pct_change,
            currency=m.currency,
        )
        for m in moves
    ]
