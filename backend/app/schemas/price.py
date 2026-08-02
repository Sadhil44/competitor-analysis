from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PriceObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    price: Decimal | None
    currency: str
    in_stock: bool
    promo_text: str
    observed_at: datetime
    source: str


class PriceTrend(BaseModel):
    product_id: int
    product_name: str
    observations: list[PriceObservationRead]
    latest_price: Decimal | None
    price_change: Decimal | None
    price_change_pct: float | None
