from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Product(Base):
    """A product listing discovered on a competitor's site.

    Discovered by the scraper expanding a competitor's `catalog_urls`
    (see config/competitors.yaml) — not config-driven itself. `sku` is
    nullable because it's often not visible on a listing page; when
    present it's indexed for lookups, but product identity for
    find-or-create matching is currently by (competitor_id, name) — see
    app/scraping/ingest.py.
    """

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"))
    sku: Mapped[str | None] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(500))
    # Size/quality variant (e.g. "8-9 CM", "PREMIUM") — populated by the
    # first-party feed import (app/scraping/feed_import.py); a given sku in
    # that feed never carries more than one grade, so this stays a plain
    # column rather than folding into product identity.
    grade: Mapped[str | None] = mapped_column(String(100), default=None)
    category: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())

    competitor: Mapped["Competitor"] = relationship(back_populates="products")
    price_observations: Mapped[list["PriceObservation"]] = relationship(back_populates="product")
