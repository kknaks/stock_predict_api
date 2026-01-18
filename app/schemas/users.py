"""
사용자 관련 스키마
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.enums import UserRole


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
    account_balance: Decimal
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserProfileResponse(BaseModel):
    """사용자 프로필 응답"""
    uid: int
    nickname: str
    role: UserRole
    accounts: list[AccountResponse] = []
    
    class Config:
        from_attributes = True
