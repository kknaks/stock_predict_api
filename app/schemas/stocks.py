"""
주식 관련 스키마
"""

from pydantic import BaseModel, Field
from app.core.enums import StrategyStatus


class CreateStrategyRequest(BaseModel):
    strategy_id: int = Field(..., description="전략 ID")
    ls_ratio: float = Field(..., description="손절 비율")
    tp_ratio: float = Field(..., description="익절 비율")

class UpdateStrategyRequest(BaseModel):
    strategy_id: int = Field(..., description="전략 ID")
    ls_ratio: float = Field(..., description="손절 비율")
    tp_ratio: float = Field(..., description="익절 비율")
    status: StrategyStatus = Field(..., description="전략 상태")
    is_auto: bool = Field(..., description="자동 실행 여부")

class StrategyInfoDetail(BaseModel):
    id: int
    name: str
    description: str | None

    class Config:
        from_attributes = True


class CreateStrategyResponse(BaseModel):
    id: int
    ls_ratio: float
    tp_ratio: float
    strategy_info: StrategyInfoDetail

    class Config:
        from_attributes = True


class UpdateStrategyResponse(BaseModel):
    id: int
    ls_ratio: float
    tp_ratio: float
    status: StrategyStatus
    is_auto: bool
    strategy_info: StrategyInfoDetail

    class Config:
        from_attributes = True
