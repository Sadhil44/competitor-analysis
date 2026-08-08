from datetime import datetime

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
