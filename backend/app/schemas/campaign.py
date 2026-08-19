from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DetectedCampaign(BaseModel):
    """A promo/campaign candidate found while crawling a page — not yet
    persisted. `starts_at`/`ends_at` are omitted entirely (not just
    Optional) because detection never states dates that aren't literally
    present in the source text; the caller decides whether/how to persist.
    """

    title: str
    description: str
    discount_text: str = ""
    source_url: str
    # Set by the crawl orchestrator (app/scraping/ingest.py), which has the
    # DB session/product row — campaigns.py itself has no DB access and
    # can't resolve a product id.
    product_id: int | None = None


class CampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    competitor_id: int
    product_id: int | None
    title: str
    description: str
    discount_text: str
    starts_at: datetime | None
    ends_at: datetime | None
    source_url: str
    discovered_at: datetime
