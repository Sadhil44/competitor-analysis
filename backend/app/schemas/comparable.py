from decimal import Decimal

from pydantic import BaseModel


class ComparableProduct(BaseModel):
    id: int
    name: str
    competitor_id: int
    competitor_slug: str
    competitor_name: str
    latest_price: Decimal | None
    currency: str | None
