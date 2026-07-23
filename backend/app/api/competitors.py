from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Competitor, Product
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
async def list_competitor_products(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Competitor).where(Competitor.slug == slug))
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise HTTPException(status_code=404, detail=f"No competitor with slug {slug!r}")

    result = await db.execute(select(Product).where(Product.competitor_id == competitor.id))
    return result.scalars().all()
