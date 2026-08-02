from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SWOTAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    competitor_id: int
    strengths: list[str]
    weaknesses: list[str]
    opportunities: list[str]
    threats: list[str]
    generated_at: datetime
    model_used: str
    source_summary: str
