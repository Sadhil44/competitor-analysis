from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
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
    # brand/description/image_url mirror ExtractedProduct's own top-level
    # fields (app/schemas/extraction.py) — extracted by the scraper from day
    # one but never persisted until now (see app/scraping/ingest.py).
    brand: Mapped[str | None] = mapped_column(String(255), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    image_url: Mapped[str | None] = mapped_column(Text, default=None)
    # Free-form comparison attributes (material, height/depth, form,
    # configuration, bundle_qty, features, claims, price_basis, ...) — one
    # flexible JSONB column rather than a rigid column per attribute, since
    # which attributes matter is category-specific (raised beds care about
    # material/height; a different category would care about different
    # things) and this stays small enough per-product for in-Python scoring
    # (see app/intelligence/matching.py) rather than needing JSONB queries.
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())

    competitor: Mapped["Competitor"] = relationship(back_populates="products")
    price_observations: Mapped[list["PriceObservation"]] = relationship(back_populates="product")
