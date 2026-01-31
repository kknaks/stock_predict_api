"""
모델 리포트 관련 스키마
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ReportListItem(BaseModel):
    id: int
    version: str
    status: str
    trigger_type: Optional[str] = None
    training_samples: Optional[int] = None
    training_data_start: Optional[str] = None
    training_data_end: Optional[str] = None
    training_duration_seconds: Optional[float] = None
    created_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReportListResponse(BaseModel):
    data: list[ReportListItem]


class ReportDetailResponse(BaseModel):
    version: str
    status: str
    content: str
