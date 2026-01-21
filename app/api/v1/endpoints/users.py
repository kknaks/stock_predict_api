"""
사용자 API 엔드포인트
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession
from app.core.permissions import CurrentUser, RequireMaster
from app.services.user_service import UserService
from app.schemas.users import (
    CreateAccountRequest,
    AccountResponse,
    UserProfileResponse,
)

router = APIRouter()


@router.get("/me", response_model=UserProfileResponse)
async def get_current_user(current_user: CurrentUser, db: DbSession):
    """현재 로그인한 사용자 정보 (계좌 포함)"""
    service = UserService(db)
    user = await service.get_user_with_accounts(current_user.uid)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다",
        )

    return user


@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    request: CreateAccountRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """새 계좌 등록"""
    service = UserService(db)

    if await service.check_account_exists(request.account_number):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 등록된 계좌번호입니다",
        )

    account = await service.create_account(current_user.uid, request)
    return account