from datetime import datetime
from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field


class PositionStatus(str, Enum):
    """포지션 상태"""
    HOLDING = "holding"              # 보유 중
    TARGET_REACHED = "target_reached"  # 목표가 도달 (익절)
    STOP_LOSS = "stop_loss"          # 손절
    SOLD = "sold"                    # 매도 완료


class StockPosition(BaseModel):
    """종목별 포지션 정보"""
    # 기본 정보
    stock_code: str = Field(..., description="종목코드")
    stock_name: str = Field(..., description="종목명")

    # 매수 정보
    buy_price: Optional[float] = Field(None, description="매수 평균단가")
    buy_quantity: Optional[int] = Field(None, description="매수 수량")
    buy_amount: Optional[float] = Field(None, description="매수 금액 (매수가 * 수량)")

    # 매도 정보
    sell_price: Optional[float] = Field(None, description="매도가")
    sell_quantity: Optional[int] = Field(None, description="매도 수량")
    sell_amount: Optional[float] = Field(None, description="매도 금액")

    # 보유 정보
    holding_quantity: int = Field(0, description="현재 보유수량")
    current_price: Optional[int] = Field(None, description="현재가")
    eval_amount: Optional[float] = Field(None, description="평가금액 (현재가 * 보유수량)")

    # 목표가/손절가 정보
    target_price: Optional[float] = Field(None, description="목표가")
    stop_loss_price: Optional[float] = Field(None, description="손절가")

    # 수익 정보
    profit_rate: Optional[float] = Field(None, description="수익률 (%)")
    profit_amount: Optional[float] = Field(None, description="수익 금액")

    # 상태
    status: PositionStatus = Field(PositionStatus.HOLDING, description="포지션 상태")

    # 주문 정보
    order_count: int = Field(0, description="주문 건수")
    last_order_at: Optional[datetime] = Field(None, description="마지막 주문 시각")

    class Config:
        from_attributes = True


class TdPositionSummary(BaseModel):
    """잔고 요약 정보"""
    # 실현 손익 (매도 완료)
    realized_profit_amount: float = Field(0, description="실현손익 (매도 완료된 종목)")

    # 미실현 (보유 중인 종목)
    holding_buy_amount: float = Field(0, description="보유 종목 매입금액")
    holding_eval_amount: float = Field(0, description="보유 종목 평가금액")
    holding_profit_amount: float = Field(0, description="보유 종목 평가손익")
    holding_profit_rate: float = Field(0, description="보유 종목 수익률 (%)")

    # 종목 수
    total_holding_count: int = Field(0, description="보유 종목 수")
    total_sold_count: int = Field(0, description="매도 완료 종목 수")
    total_target_reached_count: int = Field(0, description="목표가 도달 종목 수")
    total_stop_loss_count: int = Field(0, description="손절 종목 수")


class TdPositionResponse(BaseModel):
    """잔고 조회 응답"""
    # 조회 기준
    user_id: int = Field(..., description="사용자 ID")
    date: str = Field(..., description="조회 날짜 (YYYY-MM-DD)")
    daily_strategy_id: Optional[int] = Field(None, description="일별 전략 ID")

    # 요약 정보
    summary: TdPositionSummary = Field(..., description="잔고 요약")

    # 종목별 상세
    positions: List[StockPosition] = Field(default_factory=list, description="종목별 포지션")

    # 메타 정보
    updated_at: Optional[datetime] = Field(None, description="마지막 업데이트 시각")

    class Config:
        from_attributes = True
