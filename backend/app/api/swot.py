from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Competitor, SWOTAnalysis
from app.schemas.swot import SWOTAnalysisRead

router = APIRouter(prefix="/competitors", tags=["swot"])


async def _get_competitor_or_404(slug: str, db: AsyncSession) -> Competitor:
    result = await db.execute(select(Competitor).where(Competitor.slug == slug))
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise HTTPException(status_code=404, detail=f"No competitor with slug {slug!r}")
    return competitor


@router.get("/{slug}/swot", response_model=SWOTAnalysisRead)
async def get_latest_swot(slug: str, db: AsyncSession = Depends(get_db)):
    competitor = await _get_competitor_or_404(slug, db)
    result = await db.execute(
        select(SWOTAnalysis)
        .where(SWOTAnalysis.competitor_id == competitor.id)
        .order_by(SWOTAnalysis.generated_at.desc())
        .limit(1)
    )
    swot = result.scalar_one_or_none()
    if swot is None:
        raise HTTPException(status_code=404, detail=f"No SWOT analysis exists yet for {slug!r}")
    return swot


@router.get("/{slug}/swot/history", response_model=list[SWOTAnalysisRead])
async def get_swot_history(slug: str, db: AsyncSession = Depends(get_db)):
    # SWOTAnalysis rows are never overwritten (see the model's docstring) —
    # this is what makes "how has our view of this competitor changed"
    # answerable, not just "what's the current view."
    competitor = await _get_competitor_or_404(slug, db)
    result = await db.execute(
        select(SWOTAnalysis)
        .where(SWOTAnalysis.competitor_id == competitor.id)
        .order_by(SWOTAnalysis.generated_at.desc())
    )
    return result.scalars().all()
