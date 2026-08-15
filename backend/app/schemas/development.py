from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DevelopmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    competitor_id: int
    title: str
    summary: str
    url: str
    category: str
    event_date: datetime
    discovered_at: datetime
