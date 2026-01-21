"""
인증 API 엔드포인트
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.permissions import CurrentUser
from app.config import settings
from app.core.enums import UserRole
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.database.database.users import Users
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterMasterRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

from datetime import timedelta

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: DbSession):
    """
    일반 사용자 회원가입
    
    - 닉네임 중복 체크
    - 비밀번호 SHA-256 해싱
    - 기본 역할: USER
    """
    # 닉네임 중복 체크
    existing = await db.execute(
        select(Users).where(Users.nickname == request.nickname)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 존재하는 닉네임입니다",
        )
    
    # 사용자 생성
    user = Users(
        nickname=request.nickname,
        password_hash=hash_password(request.password),
        role=request.role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    
    return user


@router.post("/register/master", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_master(request: RegisterMasterRequest, db: DbSession):
    """
    마스터 계정 생성
    
    - master_secret_key가 일치해야 생성 가능
    - 역할: MASTER
    """
    # 시크릿 키 검증
    if request.master_secret_key != settings.master_secret_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="마스터 시크릿 키가 올바르지 않습니다",
        )
    
    # 닉네임 중복 체크
    existing = await db.execute(
        select(Users).where(Users.nickname == request.nickname)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 존재하는 닉네임입니다",
        )
    
    # 마스터 계정 생성
    user = Users(
        nickname=request.nickname,
        password_hash=hash_password(request.password),
        role=UserRole.MASTER,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    
    return user


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: DbSession):
    """
    로그인 (닉네임 + 비밀번호)
    
    - 비밀번호 검증
    - JWT 토큰 발급
    """
    # 사용자 조회
    result = await db.execute(
        select(Users).where(Users.nickname == request.nickname)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="닉네임 또는 비밀번호가 올바르지 않습니다",
        )
    
    # 비밀번호 검증
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="닉네임 또는 비밀번호가 올바르지 않습니다",
        )
    
    # 토큰 생성
    token_data = {
        "sub": str(user.uid),  # JWT 표준: sub는 문자열이어야 함
        "nickname": user.nickname,
        "role": user.role.value,
    }

    # test
    # expires_delta = timedelta(seconds=10)
    # access_token = create_access_token(token_data, expires_delta)
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    
    # DB에 토큰 저장
    user.access_token = access_token
    user.refresh_token = refresh_token
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest, db: DbSession):
    """
    토큰 갱신
    
    - Refresh Token으로 새 Access Token 발급
    """
    # 토큰 검증
    payload = decode_token(request.refresh_token)
    
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 Refresh Token입니다",
        )
    
    # 사용자 조회
    result = await db.execute(
        select(Users).where(Users.uid == int(payload.get("sub")))
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다",
        )
    
    # 새 토큰 생성
    token_data = {
        "sub": str(user.uid),  # JWT 표준: sub는 문자열이어야 함
        "nickname": user.nickname,
        "role": user.role.value,
    }
    
    new_access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)
    
    # DB 업데이트
    user.access_token = new_access_token
    user.refresh_token = new_refresh_token
    
    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
    )


@router.post("/logout")
async def logout(
    db: DbSession,
    current_user: CurrentUser,
):
    """
    로그아웃
    
    - DB에서 토큰 삭제
    - 클라이언트에서도 토큰 삭제 필요
    """
    # 사용자 조회
    result = await db.execute(
        select(Users).where(Users.uid == current_user.uid)
    )
    user = result.scalar_one_or_none()
    
    if user:
        user.access_token = None
        user.refresh_token = None
    
    return {"message": "로그아웃 되었습니다"}
