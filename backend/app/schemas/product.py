from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    competitor_id: int
    sku: str | None
    name: str
    grade: str | None
    category: str
    url: str
    first_seen_at: datetime
    last_seen_at: datetime
    # Populated only by the list endpoint (GET /competitors/{slug}/products),
    # which batches in each product's latest observation — None here on the
    # single-product endpoint (GET /products/{id}), which doesn't fetch it.
    latest_price: Decimal | None = None
    currency: str | None = None
    in_stock: bool | None = None
