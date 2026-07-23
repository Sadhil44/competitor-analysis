from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CompetitorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    website_url: str
    notes: str
    created_at: datetime

