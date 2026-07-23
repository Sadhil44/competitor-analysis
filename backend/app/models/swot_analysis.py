from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class SWOTAnalysis(Base):
    """A generated SWOT analysis for a competitor, as of a point in time.

    History is kept, not overwritten — each generation (scheduled or
    on-demand) inserts a new row rather than updating an existing one, so
    "how has our view of this competitor changed" is itself answerable.
    Written by the swot_agent subagent (Phase 3).
    """

    __tablename__ = "swot_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"))
    strengths: Mapped[list[str]] = mapped_column(ARRAY(Text))
    weaknesses: Mapped[list[str]] = mapped_column(ARRAY(Text))
    opportunities: Mapped[list[str]] = mapped_column(ARRAY(Text))
    threats: Mapped[list[str]] = mapped_column(ARRAY(Text))
    generated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    model_used: Mapped[str] = mapped_column(String(100))
    source_summary: Mapped[str] = mapped_column(Text)

    competitor: Mapped["Competitor"] = relationship(back_populates="swot_analyses")
