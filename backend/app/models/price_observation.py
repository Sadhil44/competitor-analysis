from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class PriceObservation(Base):
    """A single point-in-time price reading for a product.

    Append-only time series — never updated, never deleted. One row per
    scrape (or per agent live-fetch). Price trends and price-change
    detection work by comparing rows, not by mutating a "current price"
    field.
    """

    __tablename__ = "price_observations"

    # The first-party feed (source="internal_feed") derives observed_at from
    # a season code rather than a real timestamp, so re-running the same
    # import file would otherwise insert duplicate rows every time. This
    # partial unique index makes that import idempotent via
    # ON CONFLICT DO NOTHING (see app/scraping/feed_import.py) without
    # constraining scraped rows, whose observed_at is a real high-resolution
    # timestamp that's never expected to collide.
    __table_args__ = (
        Index(
            "ix_price_observations_internal_feed_dedup",
            "product_id",
            "observed_at",
            "source",
            unique=True,
            postgresql_where=text("source = 'internal_feed'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    # Nullable: some listings show no price at all for out-of-stock/"notify
    # me" items — there's nothing to round-trip through Decimal in that case.
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    in_stock: Mapped[bool] = mapped_column()
    promo_text: Mapped[str] = mapped_column(Text, default="")
    observed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    source: Mapped[str] = mapped_column(String(50))

    product: Mapped["Product"] = relationship(back_populates="price_observations")