"""
인증 관련 스키마
"""

from pydantic import BaseModel, Field

from app.core.enums import UserRole


class RegisterRequest(BaseModel):
    """회원가입 요청"""
    nickname: str = Field(..., min_length=2, max_length=50, description="닉네임 (로그인 ID)")
    password: str = Field(..., min_length=4, description="비밀번호")
    role: UserRole = Field(..., description="역할")


class RegisterMasterRequest(BaseModel):
    """마스터 계정 생성 요청"""
    nickname: str = Field(..., min_length=2, max_length=50, description="닉네임 (로그인 ID)")
    password: str = Field(..., min_length=4, description="비밀번호")
    master_secret_key: str = Field(..., description="마스터 시크릿 키")


class LoginRequest(BaseModel):
    """로그인 요청"""
    nickname: str = Field(..., description="닉네임")
    password: str = Field(..., description="비밀번호")


class TokenResponse(BaseModel):
    """토큰 응답"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """토큰 갱신 요청"""
    refresh_token: str


class UserResponse(BaseModel):
    """사용자 정보 응답"""
    uid: int
    nickname: str
    role: UserRole
    
    class Config:
        from_attributes = True
