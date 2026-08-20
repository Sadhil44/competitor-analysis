from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CompetitorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    website_url: str
    notes: str
    is_own_brand: bool
    brand_num: int | None
    created_at: datetime
    # Aggregates for the dashboard — not real columns on Competitor, filled
    # in by the endpoint from Product/CrawlRun rather than from_attributes.
    product_count: int = 0
    last_crawled_at: datetime | None = None
    last_crawl_status: str | None = None

