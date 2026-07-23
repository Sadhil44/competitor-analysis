from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Product(Base):
    """A product listing discovered on a competitor's site.

    Discovered by the scraper expanding a competitor's `catalog_urls`
    (see config/competitors.yaml) — not config-driven itself. `sku` is
    indexed because the scraper looks products up by it on every crawl to
    decide "new product" vs. "product we've already seen".
    """

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"))
    sku: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())

    competitor: Mapped["Competitor"] = relationship(back_populates="products")
    price_observations: Mapped[list["PriceObservation"]] = relationship(back_populates="product")
