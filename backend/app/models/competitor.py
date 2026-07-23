from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Competitor(Base):
    """Seeded from config/competitors.yaml (see app/core/config.py).

    Kept as a real DB table (not just read from YAML at request time) so
    Product/PriceObservation/SWOTAnalysis/Development/CrawlRun rows can FK
    to a stable id, and so the API can serve competitor metadata without
    re-parsing YAML on every request.
    """

    __tablename__ = "competitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    website_url: Mapped[str] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    products: Mapped[list["Product"]] = relationship(back_populates="competitor")
    swot_analyses: Mapped[list["SWOTAnalysis"]] = relationship(back_populates="competitor")
    developments: Mapped[list["Development"]] = relationship(back_populates="competitor")
    crawl_runs: Mapped[list["CrawlRun"]] = relationship(back_populates="competitor")
