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

    # True for our own brands (Gurney's, Spring Hill Nurseries, Breck's, ...)
    # as opposed to real competitors — same Product/PriceObservation shape,
    # just a different provenance, so agent tools and the dashboard can
    # filter "us" vs "them" without a parallel schema. `brand_num` is the
    # internal brand code from the first-party pricing feed
    # (config/own_brands.yaml / app/scraping/feed_import.py); null for
    # competitors seeded from competitors.yaml.
    is_own_brand: Mapped[bool] = mapped_column(default=False, server_default="false")
    brand_num: Mapped[int | None] = mapped_column(unique=True, default=None)

    products: Mapped[list["Product"]] = relationship(back_populates="competitor")
    swot_analyses: Mapped[list["SWOTAnalysis"]] = relationship(back_populates="competitor")
    developments: Mapped[list["Development"]] = relationship(back_populates="competitor")
    crawl_runs: Mapped[list["CrawlRun"]] = relationship(back_populates="competitor")
