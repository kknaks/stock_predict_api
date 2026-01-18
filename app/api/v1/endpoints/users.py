"""
사용자 API 엔드포인트
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession
from app.core.permissions import CurrentUser, RequireMaster
from app.repositories.user_repository import UserRepository
from app.services.account_service import AccountService
from app.schemas.users import (
    CreateAccountRequest,
    AccountResponse,
    UserProfileResponse,
)

router = APIRouter()


@router.get("/me", response_model=UserProfileResponse)
async def get_current_user(current_user: CurrentUser, db: DbSession):
    """현재 로그인한 사용자 정보 (계좌 포함)"""
    repo = UserRepository(db)
    user = await repo.get_by_uid_with_accounts(current_user.uid)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다",
        )
    
    return user


@router.get("/{user_id}", response_model=UserProfileResponse, dependencies=[RequireMaster])
async def get_user(user_id: int, db: DbSession):
    """사용자 정보 조회 (관리자 전용)"""
    repo = UserRepository(db)
    user = await repo.get_by_uid_with_accounts(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다",
        )
    
    return user


@router.post("/me/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    current_user: CurrentUser,
    request: CreateAccountRequest,
    db: DbSession,
):
    service = AccountService(db)
    
    try:
        account = await service.create_account(
            user_uid=current_user.uid,
            account_number=request.account_number,
            app_key=request.app_key,
            app_secret=request.app_secret,
            is_paper=request.is_paper,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return account


@router.get("/me/accounts", response_model=list[AccountResponse])
async def get_my_accounts(current_user: CurrentUser, db: DbSession):
    """내 계좌 목록 조회"""
    service = AccountService(db)
    accounts = await service.get_user_accounts(current_user.uid)
    return accounts


@router.delete("/me/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: int, current_user: CurrentUser, db: DbSession):
    """계좌 삭제"""
    service = AccountService(db)
    deleted = await service.delete_account(account_id, current_user.uid)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="계좌를 찾을 수 없습니다",
        )


@router.get("/me/accounts/{account_id}/balance")
async def get_account_balance(account_id: int, current_user: CurrentUser, db: DbSession):
    """계좌 잔고 조회 (KIS API 실시간)"""
    service = AccountService(db)
    account = await service.get_user_account(account_id, current_user.uid)
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="계좌를 찾을 수 없습니다",
        )
    
    try:
        balance = await service.get_account_balance(account)
        return balance
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"잔고 조회 실패: {str(e)}",
        )
