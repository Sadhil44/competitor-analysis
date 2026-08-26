from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class BrandSummary(BaseModel):
    competitor_slug: str
    competitor_name: str
    is_own_brand: bool
    product_count: int
    median_price: Decimal | None
    min_price: Decimal | None
    max_price: Decimal | None
    promo_share: float  # 0-1
    in_stock_share: float  # 0-1
    last_crawled_at: datetime | None
    last_crawl_status: str | None
    pages_fetched: int | None


class RaisedBedSummary(BaseModel):
    generated_at: datetime
    scope_note: str
    brands: list[BrandSummary]


class MatrixCell(BaseModel):
    competitor_slug: str
    material: str
    height_band: str
    form: str
    count: int


class RaisedBedMatrix(BaseModel):
    cells: list[MatrixCell]
    # Products included in the matrix have all three axes recorded; this is
    # how many in-scope products were excluded for missing at least one —
    # shown so the matrix doesn't silently imply more coverage than it has.
    excluded_incomplete_count: int


class RaisedBedProduct(BaseModel):
    id: int
    name: str
    url: str
    latest_price: Decimal | None
    currency: str | None
    in_stock: bool | None
    material: str | None
    height_band: str | None
    form: str | None
    footprint: str | None


class PriceMoveOut(BaseModel):
    product_id: int
    product_name: str
    product_url: str
    competitor_slug: str
    competitor_name: str
    is_own_brand: bool
    first_price: Decimal
    last_price: Decimal
    pct_change: float
    currency: str


class OpportunityOut(BaseModel):
    material: str
    height_band: str
    form: str
    kind: str  # "gap" | "strength"
    own_count: int
    competitor_counts: dict[str, int]
    total_competitor_count: int


class OpportunityAnalysis(BaseModel):
    own_brand_slug: str
    gaps: list[OpportunityOut]
    strengths: list[OpportunityOut]


class ComparableMatch(BaseModel):
    product_id: int
    name: str
    url: str
    competitor_slug: str
    competitor_name: str
    latest_price: Decimal | None
    currency: str | None
    score: int
    confidence: str
    matched_fields: list[str]
    missing_fields: list[str]
