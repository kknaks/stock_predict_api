"""
예측 관련 스키마
"""

from datetime import date
from typing import Optional
from pydantic import BaseModel, Field


class PredictionItem(BaseModel):
    """예측 결과 아이템"""

    id: int = Field(..., description="예측 ID")
    timestamp: date = Field(..., description="예측 시각")
    stock_code: str = Field(..., description="종목 코드")
    stock_name: str = Field(..., description="종목명")
    exchange: Optional[str] = Field(None, description="거래소 (KOSPI/KOSDAQ)")
    prediction_date: date = Field(..., description="예측 대상 날짜")
    gap_rate: float = Field(..., description="갭 상승률 (%)")
    stock_open: float = Field(..., description="당일 시가")
    prob_up: float = Field(..., description="상승 확률 (0~1)")
    prob_down: float = Field(..., description="하락 확률 (0~1)")
    predicted_direction: int = Field(..., description="예측 방향 (0:하락, 1:상승)")
    expected_return: float = Field(..., description="기대 수익률 (%)")
    return_if_up: float = Field(..., description="상승 시 예상 수익률 (%)")
    return_if_down: float = Field(..., description="하락 시 예상 손실률 (%)")
    max_return_if_up: Optional[float] = Field(None, description="상승 시 최대 수익률 (%)")
    take_profit_target: Optional[float] = Field(None, description="익절 목표 수익률 (%)")
    signal: str = Field(..., description="매매 신호 (BUY/HOLD/SELL)")
    model_version: str = Field(..., description="모델 버전")
    confidence: Optional[str] = Field(None, description="신뢰도 (HIGH/MEDIUM/LOW)")
    actual_close: Optional[float] = Field(None, description="실제 종가")
    actual_high: Optional[float] = Field(None, description="실제 고가")
    actual_low: Optional[float] = Field(None, description="실제 저가")
    actual_return: Optional[float] = Field(None, description="실제 종가 수익률 (%)")
    return_diff: Optional[float] = Field(None, description="종가 예측 차이")
    actual_max_return: Optional[float] = Field(None, description="실제 고가 수익률 (%)")
    max_return_diff: Optional[float] = Field(None, description="고가 예측 차이")
    direction_correct: Optional[int] = Field(None, description="예측 방향 정확도 (1: 맞음, 0: 틀림)")

    class Config:
        from_attributes = True
