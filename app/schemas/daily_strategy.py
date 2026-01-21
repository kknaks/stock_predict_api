from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class DailyStrategyStock(BaseModel):
    """일일 전략별 종목 정보"""
    stock_code: str
    stock_name: str
    exchange: str
    stock_open: int
    target_price: Optional[float] = None
    target_quantity: Optional[int] = None
    target_sell_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    gap_rate: Optional[float] = None
    take_profit_target: Optional[float] = None
    prob_up: Optional[float] = None
    signal: str
    created_at: datetime

    @field_validator('target_price', 'target_sell_price', 'take_profit_target', 'prob_up', mode='before')
    @classmethod
    def parse_string_to_float(cls, v):
        """문자열로 된 숫자를 float로 변환"""
        if isinstance(v, str):
            try:
                return float(v)
            except (ValueError, TypeError):
                return None
        return v

    @field_validator('target_quantity', mode='before')
    @classmethod
    def parse_string_to_float(cls, v):
        """문자열로 된 숫자를 int로 변환"""
        if isinstance(v, str):
            try:
                return int(v)
            except (ValueError, TypeError):
                return None
        return v


class DailyStrategy(BaseModel):
    """사용자별 전략 정보"""
    user_strategy_id: int
    user_id: int
    strategy_id: int
    strategy_name: str
    strategy_weight_type: str
    ls_ratio: float
    tp_ratio: float
    stocks: List[DailyStrategyStock]


class StrategiesByUser(BaseModel):
    """사용자별 전략 목록"""
    user_id: int
    strategies: List[DailyStrategy]


class DailyStrategyMessage(BaseModel):
    """일일 전략 메시지 (최상위 구조)"""
    timestamp: datetime
    strategies_by_user: List[StrategiesByUser] = Field(alias="strategies_by_user")

    class Config:
        populate_by_name = True
