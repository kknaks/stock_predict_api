"""
전략 API 엔드포인트
"""

from typing import List

from fastapi import APIRouter, HTTPException, status, Query

from app.api.deps import DbSession
from app.core.permissions import CurrentUser
from app.services.strategy_service import StrategyService
from app.services.account_service import AccountService
from app.schemas.users import (
    CreateStrategyRequest,
    CreateStrategyResponse,
    UpdateStrategyRequest,
    UpdateStrategyResponse,
    StrategyInfoResponse,
    StrategyWeightTypeResponse,
)

router = APIRouter()


@router.post("", response_model=CreateStrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    request: CreateStrategyRequest,
    db: DbSession,
    current_user: CurrentUser,
    account_id: int = Query(..., description="계좌 ID"),
):
    """
    전략 생성

    - 계좌에 새 전략 생성
    """
    # 계좌 소유권 확인
    account_service = AccountService(db)
    account = await account_service.get_user_account(account_id, current_user.uid)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="계좌를 찾을 수 없거나 권한이 없습니다",
        )

    service = StrategyService(db)
    return await service.create_strategy(account_id, request)


@router.get("/info", response_model=List[StrategyInfoResponse], status_code=status.HTTP_200_OK)
async def get_strategy_info(db: DbSession):
    """전략 정보 목록 조회"""
    service = StrategyService(db)
    return await service.get_all_strategy_info()


@router.get("/weight-types", response_model=List[StrategyWeightTypeResponse], status_code=status.HTTP_200_OK)
async def get_strategy_weight_types(db: DbSession):
    """가중치 타입 목록 조회"""
    service = StrategyService(db)
    return await service.get_all_strategy_weight_types()


@router.patch("/{strategy_id}", response_model=UpdateStrategyResponse, status_code=status.HTTP_200_OK)
async def update_strategy(
    strategy_id: int,
    request: UpdateStrategyRequest,
    db: DbSession,
    current_user: CurrentUser,
    account_id: int = Query(..., description="계좌 ID"),
):
    """
    전략 업데이트

    - 계좌 소유자만 수정 가능
    - 부분 업데이트 지원 (PATCH)
    - status를 ACTIVE로 변경하면 해당 계좌의 다른 전략은 INACTIVE가 됨
    """
    # 계좌 소유권 확인
    account_service = AccountService(db)
    account = await account_service.get_user_account(account_id, current_user.uid)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="계좌를 찾을 수 없거나 권한이 없습니다",
        )

    service = StrategyService(db)
    result = await service.update_strategy(strategy_id, account_id, request)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="전략을 찾을 수 없거나 권한이 없습니다",
        )

    return result


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: int,
    db: DbSession,
    current_user: CurrentUser,
    account_id: int = Query(..., description="계좌 ID"),
):
    """
    전략 삭제 (소프트 삭제)

    - 계좌 소유자만 삭제 가능
    - is_auto=False, status=inactive, is_deleted=True로 변경
    """
    # 계좌 소유권 확인
    account_service = AccountService(db)
    account = await account_service.get_user_account(account_id, current_user.uid)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="계좌를 찾을 수 없거나 권한이 없습니다",
        )

    service = StrategyService(db)
    deleted = await service.delete_strategy(strategy_id, account_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="전략을 찾을 수 없거나 권한이 없습니다",
        )
