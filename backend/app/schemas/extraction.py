from decimal import Decimal

from pydantic import BaseModel


class ExtractedProduct(BaseModel):
    sku: str | None = None
    name: str
    price: Decimal
    currency: str
    in_stock: bool
    promo_text: str = ""


class ExtractedProductList(BaseModel):
    products: list[ExtractedProduct]
