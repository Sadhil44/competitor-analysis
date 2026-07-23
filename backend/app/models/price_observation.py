from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Text
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

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3))
    in_stock: Mapped[bool] = mapped_column()
    promo_text: Mapped[str] = mapped_column(Text, default="")
    observed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    source: Mapped[str] = mapped_column(String(50))

    product: Mapped["Product"] = relationship(back_populates="price_observations")