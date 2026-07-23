from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Development(Base):
    """A piece of competitor news/PR: launches, promos, funding, leadership,
    or other developments.

    `embedding` backs semantic search (search_developments agent tool,
    Phase 3) via pgvector — generated from `title` + `summary` using Voyage
    AI at write time. Written by the developments_agent subagent, and by
    the scraping pipeline for anything discovered during a scheduled crawl.
    """

    __tablename__ = "developments"

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"))
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50))
    event_date: Mapped[datetime] = mapped_column()
    discovered_at: Mapped[datetime] = mapped_column(server_default=func.now())
    embedding: Mapped[list[float]] = mapped_column(Vector(1024))

    competitor: Mapped["Competitor"] = relationship(back_populates="developments")
