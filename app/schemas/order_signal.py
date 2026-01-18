from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator

class OrderSignalMessage(BaseModel):
    """주문 시그널 메시지 (기존 호환성 유지)"""
    timestamp: datetime
    user_strategy_id: int
    signal_type: str
    stock_code: str
    current_price: float
    target_price: float
    target_quantity: int
    stop_loss_price: float
    recommended_order_price: float
    recommended_order_type: str
    expected_slippage_pct: float
    urgency: str
    reason: str

    @field_validator('user_strategy_id','current_price', 'stop_loss_price', 'recommended_order_price', 'expected_slippage_pct', mode='before')
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


class OrderResultMessage(BaseModel):
    """주문 결과 메시지 (주문 접수 및 체결통보)"""
    timestamp: datetime
    user_strategy_id: int
    order_type: str  # BUY or SELL
    stock_code: str
    order_no: str  # 주문번호 (필수)
    order_quantity: int
    order_price: float
    order_dvsn: str  # 주문구분 (00: 지정가, 01: 시장가 등)
    account_no: str
    is_mock: bool
    status: str  # ordered, partially_executed, executed
    executed_quantity: int  # 이번 체결 수량
    executed_price: float  # 이번 체결 가격
    # 부분 체결 정보
    total_executed_quantity: int  # 누적 체결 수량
    total_executed_price: float  # 누적 체결 가격 (가중평균)
    remaining_quantity: int  # 남은 수량
    is_fully_executed: bool  # 전량 체결 여부

    @field_validator('user_strategy_id', 'order_quantity', 'order_price', 'executed_quantity', 
                     'executed_price', 'total_executed_quantity', 'total_executed_price', 
                     'remaining_quantity', mode='before')
    @classmethod
    def parse_string_to_float(cls, v):
        """문자열로 된 숫자를 float/int로 변환"""
        if isinstance(v, str):
            try:
                if '.' in v:
                    return float(v)
                else:
                    return int(v)
            except (ValueError, TypeError):
                return None
        return v