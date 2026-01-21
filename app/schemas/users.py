"""
사용자 관련 스키마
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.core.enums import UserRole
from app.database.database.strategy import StrategyStatus, WeightType
from app.database.database.users import AccountType

class StrategyInfoResponse(BaseModel):
    """전략 정보 응답"""
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class StrategyWeightTypeResponse(BaseModel):
    """가중치 타입 응답"""
    id: int
    weight_type: WeightType
    description: Optional[str] = None

    class Config:
        from_attributes = True


class UserStrategyResponse(BaseModel):
    """사용자 전략 응답"""
    id: int
    strategy_id: int
    investment_weight: Optional[float] = 0.9
    ls_ratio: float = 0.0
    tp_ratio: float = 0.0
    is_auto: Optional[bool] = False
    status: Optional[StrategyStatus] = StrategyStatus.ACTIVE
    strategy_info: Optional[StrategyInfoResponse] = None
    strategy_weight_type: Optional[StrategyWeightTypeResponse] = None

    class Config:
        from_attributes = True


class CreateAccountRequest(BaseModel):
    """계좌 생성 요청"""
    account_number: str = Field(..., description="계좌 번호 (형식: 12345678-01)")
    app_key: str = Field(..., description="한국투자증권 앱 키")
    app_secret: str = Field(..., description="한국투자증권 앱 시크릿")
    is_paper: bool = Field(default=False, description="모의투자 여부")


class AccountResponse(BaseModel):
    """계좌 정보 응답"""
    id: int
    account_number: str
    account_name: str
    account_type: AccountType
    account_balance: Decimal
    created_at: datetime
    user_strategies: list[UserStrategyResponse] = []

    class Config:
        from_attributes = True


class UserProfileResponse(BaseModel):
    """사용자 프로필 응답 (계좌 및 전략 포함)"""
    uid: int
    nickname: str
    role: UserRole
    accounts: list[AccountResponse] = []

    class Config:
        from_attributes = True


class CreateStrategyRequest(BaseModel):
    """전략 생성 요청"""
    strategy_id: int = Field(..., description="전략 정보 ID (StrategyInfo)")
    investment_weight: float = Field(default=0.9, ge=0, le=1, description="투자 비중 (0~1)")
    ls_ratio: float = Field(default=0.0, description="손절 비율")
    tp_ratio: float = Field(default=0.0, description="익절 비율")
    is_auto: bool = Field(default=False, description="자동 매매 여부")
    strategy_weight_type_id: Optional[int] = Field(None, description="가중치 타입 ID")


class CreateStrategyResponse(BaseModel):
    """전략 생성 응답"""
    id: int
    account_id: int
    strategy_id: int
    investment_weight: Optional[float] = None
    ls_ratio: float
    tp_ratio: float
    is_auto: Optional[bool] = None
    status: Optional[StrategyStatus] = None
    strategy_info: Optional[StrategyInfoResponse] = None
    strategy_weight_type: Optional[StrategyWeightTypeResponse] = None

    class Config:
        from_attributes = True


class UpdateStrategyRequest(BaseModel):
    """전략 업데이트 요청"""
    investment_weight: Optional[float] = Field(None, ge=0, le=1, description="투자 비중 (0~1)")
    ls_ratio: Optional[float] = Field(None, description="손절 비율")
    tp_ratio: Optional[float] = Field(None, description="익절 비율")
    is_auto: Optional[bool] = Field(None, description="자동 매매 여부")
    status: Optional[StrategyStatus] = Field(None, description="전략 상태")
    strategy_weight_type_id: Optional[int] = Field(None, description="가중치 타입 ID")


class UpdateStrategyResponse(BaseModel):
    """전략 업데이트 응답"""
    id: int
    account_id: int
    strategy_id: int
    investment_weight: Optional[float] = None
    ls_ratio: float
    tp_ratio: float
    is_auto: Optional[bool] = None
    status: Optional[StrategyStatus] = None
    strategy_weight_type_id: Optional[int] = Field(None, alias="weight_type_id")
    strategy_info: Optional[StrategyInfoResponse] = None
    strategy_weight_type: Optional[StrategyWeightTypeResponse] = None

    class Config:
        from_attributes = True
        populate_by_name = True
