from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class CrawlRun(Base):
    """One scheduled (or manual) crawl attempt for a competitor.

    Operational/audit trail: lets the dashboard show "last crawled 2h ago"
    and gives an error trail when a crawl fails. Written by the scraping
    pipeline (Phase 1 manual trigger, Phase 5 scheduler).
    """

    __tablename__ = "crawl_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"))
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(20))
    pages_fetched: Mapped[int] = mapped_column(default=0)
    error_log: Mapped[str | None] = mapped_column(Text, default=None)

    competitor: Mapped["Competitor"] = relationship(back_populates="crawl_runs")
