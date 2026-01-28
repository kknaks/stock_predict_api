"""
사용자 API 엔드포인트
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession
from app.core.permissions import CurrentUser, RequireMaster
from app.services.user_service import UserService
from app.services.account_service import AccountService
from app.schemas.users import (
    VerifyAccountRequest,
    VerifyAccountResponse,
    CreateAccountRequest,
    UpdateAccountRequest,
    AccountResponse,
    AccountDetailResponse,
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


@router.post("/accounts/verify", response_model=VerifyAccountResponse)
async def verify_account(
    request: VerifyAccountRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """계좌 인증 (REAL/PAPER - KIS API 검증)"""
    service = AccountService(db)

    try:
        verify_token, account_balance = await service.verify_account(
            account_number=request.account_number,
            app_key=request.app_key,
            app_secret=request.app_secret,
            account_type=request.account_type,
            hts_id=request.hts_id,
            exclude_account_id=request.exclude_account_id,
        )
        return VerifyAccountResponse(
            verify_token=verify_token,
            account_balance=account_balance,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    request: CreateAccountRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    계좌 등록

    - REAL/PAPER: verify_token 필수 (인증 후 생성)
    - MOCK: account_type=MOCK, account_balance 필수
    """
    service = AccountService(db)

    try:
        account = await service.create_account(
            user_uid=current_user.uid,
            account_name=request.account_name,
            verify_token=request.verify_token,
            account_type=request.account_type,
            account_balance=request.account_balance,
        )
        return account
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/accounts/{account_id}", response_model=AccountDetailResponse)
async def get_account_detail(
    account_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """계좌 상세 조회"""
    service = AccountService(db)
    account = await service.get_account_detail(account_id, current_user.uid)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="계좌를 찾을 수 없습니다",
        )

    return AccountDetailResponse(
        id=account.id,
        account_number=account.account_number,
        account_name=account.account_name,
        account_type=account.account_type,
        account_balance=account.account_balance,
        hts_id=account.hts_id,
        app_key=account.app_key,
        app_secret="*" * len(account.app_secret),  # 전체 마스킹
        created_at=account.created_at,
        user_strategies=account.user_strategies,
    )


@router.patch("/accounts/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    request: UpdateAccountRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    계좌 수정

    - MOCK: account_name, account_balance 수정 가능
    - REAL/PAPER: account_name만 수정 가능 (인증 정보 수정 시 verify_token 필요)
    """
    service = AccountService(db)

    try:
        account = await service.update_account(
            account_id=account_id,
            user_uid=current_user.uid,
            account_name=request.account_name,
            account_balance=request.account_balance,
            verify_token=request.verify_token,
        )
        return account
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    계좌 삭제 (soft delete)

    - is_deleted = True
    - 민감 정보 초기화
    """
    service = AccountService(db)
    deleted = await service.delete_account(account_id, current_user.uid)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="계좌를 찾을 수 없습니다",
        )
