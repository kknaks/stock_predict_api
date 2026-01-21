from typing import List
from pydantic import BaseModel, Field


class DailyHistory(BaseModel):
    """일별 히스토리 데이터"""
    date: str = Field(..., description="날짜 (YYYY-MM-DD)")
    profit_rate: float = Field(0, description="일별 수익률 (%)")
    profit_amount: float = Field(0, description="일별 수익금")
    cumulative_profit_rate: float = Field(0, description="누적 수익률 (%)")
    cumulative_profit_amount: float = Field(0, description="누적 수익금")
    buy_amount: float = Field(0, description="매수 금액")
    sell_amount: float = Field(0, description="매도 금액")


class AccountHistoryResponse(BaseModel):
    """계좌별 월간 히스토리 응답"""
    account_id: int = Field(..., description="계좌 ID")
    account_number: str = Field(..., description="계좌번호")
    account_name: str = Field(..., description="계좌명")

    # 월간 요약
    total_profit_rate: float = Field(0, description="월간 총 수익률 (%)")
    total_profit_amount: float = Field(0, description="월간 총 수익금")
    total_buy_amount: float = Field(0, description="월간 총 매수 금액")
    total_sell_amount: float = Field(0, description="월간 총 매도 금액")
    trading_days: int = Field(0, description="거래일 수")

    # 일별 상세 데이터
    daily_histories: List[DailyHistory] = Field(
        default_factory=list,
        description="일별 히스토리 목록"
    )

    class Config:
        from_attributes = True


class HistoryResponse(BaseModel):
    """월별 히스토리 응답 (전체 계좌)"""
    year: int = Field(..., description="연도")
    month: int = Field(..., description="월")
    accounts: List[AccountHistoryResponse] = Field(
        default_factory=list,
        description="계좌별 히스토리 목록"
    )

    class Config:
        from_attributes = True
