"""
수동 매도 시그널 스키마
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class OrderType(str, Enum):
    """주문 유형"""
    LIMIT = "LIMIT"    # 지정가
    MARKET = "MARKET"  # 시장가


class ManualSellRequest(BaseModel):
    """수동 매도 요청"""

    daily_strategy_id: int
    stock_code: str
    order_type: OrderType
    order_price: Optional[int] = None  # 지정가인 경우 필수
    order_quantity: Optional[int] = None  # 생략 시 전량 매도


class ManualSellResponse(BaseModel):
    """수동 매도 응답"""

    success: bool
    message: str
