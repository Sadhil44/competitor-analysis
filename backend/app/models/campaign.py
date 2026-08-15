from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Campaign(Base):
    """A discovered promotional campaign — a sale, discount, or marketing
    push tied to a competitor and, when identifiable, a specific product.

    Separate from Development: Development is organizational/strategic news
    (funding, leadership, launches, assortment changes); Campaign is
    specifically pricing/promotional activity — "what campaigns is this
    competitor running on this product" doesn't fit Development, which has
    no product linkage and previously lumped promos in under a generic
    "promo" category. Append-only like Development: each discovery is a new
    row, not an update, so promo history over time is preserved.
    """

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"))
    # Nullable: some campaigns are competitor/sitewide (e.g. "20% off
    # everything") rather than tied to one product.
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), default=None)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    # Free text ("30% off", "BOGO", "$10 off orders over $50") rather than a
    # parsed numeric field — source material states discounts in whatever
    # form marketing chose, and forcing that into a single numeric percent
    # would lose or fabricate information for the common non-percent cases.
    discount_text: Mapped[str] = mapped_column(String(255), default="")
    starts_at: Mapped[datetime | None] = mapped_column(default=None)
    ends_at: Mapped[datetime | None] = mapped_column(default=None)
    source_url: Mapped[str] = mapped_column(Text, default="")
    discovered_at: Mapped[datetime] = mapped_column(server_default=func.now())

    competitor: Mapped["Competitor"] = relationship(back_populates="campaigns")
