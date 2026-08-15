from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Campaign, Competitor
from app.schemas.campaign import CampaignRead

router = APIRouter(prefix="/competitors", tags=["campaigns"])


@router.get("/{slug}/campaigns", response_model=list[CampaignRead])
async def list_campaigns(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Competitor).where(Competitor.slug == slug))
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise HTTPException(status_code=404, detail=f"No competitor with slug {slug!r}")

    result = await db.execute(
        select(Campaign)
        .where(Campaign.competitor_id == competitor.id)
        .order_by(Campaign.discovered_at.desc())
    )
    return result.scalars().all()
