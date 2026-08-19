from decimal import Decimal

from pydantic import BaseModel


class ExtractedProduct(BaseModel):
    sku: str | None = None
    name: str
    price: Decimal | None = None
    # List/"was" price alongside a current sale price, when the page states
    # one — kept separate from `price` rather than overwriting it, since
    # ingest.py needs the sale price (not the original) for PriceObservation.
    original_price: Decimal | None = None
    currency: str
    in_stock: bool
    promo_text: str = ""
    # Everything below is best-effort and additive: populated when a
    # deterministic source (JSON-LD, embedded JSON) states it, left None
    # otherwise. Not all of it has a home in the current Product model (see
    # app/scraping/ingest.py) — carried here regardless so it's available to
    # a future comparable-matching pass without re-scraping.
    category: str | None = None
    brand: str | None = None
    description: str | None = None
    image_url: str | None = None
    url: str | None = None
    attributes: dict[str, str] = {}
    # Where this record came from — "jsonld" / "embedded_json" /
    # "competitor_selector" / "generic_html" / "llm" — surfaced purely for
    # crawl logging/observability, not persisted.
    source: str = "llm"


class ExtractedProductList(BaseModel):
    products: list[ExtractedProduct]
