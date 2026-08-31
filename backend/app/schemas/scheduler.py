from datetime import datetime

from pydantic import BaseModel


class ScheduledJobRead(BaseModel):
    id: str
    competitor_slug: str
    cron: str
    next_run_time: datetime | None


class CrawlTriggerResponse(BaseModel):
    competitor_slug: str
    status: str
