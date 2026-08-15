from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Competitor, Development
from app.schemas.development import DevelopmentRead

router = APIRouter(prefix="/competitors", tags=["developments"])


@router.get("/{slug}/developments", response_model=list[DevelopmentRead])
async def list_developments(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Competitor).where(Competitor.slug == slug))
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise HTTPException(status_code=404, detail=f"No competitor with slug {slug!r}")

    result = await db.execute(
        select(Development)
        .where(Development.competitor_id == competitor.id)
        .order_by(Development.event_date.desc())
    )
    return result.scalars().all()
