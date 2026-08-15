from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
